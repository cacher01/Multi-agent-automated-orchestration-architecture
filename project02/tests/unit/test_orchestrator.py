from app.core.decision_engine import DecisionEngine
from app.core.execution_engine import ExecutionResult, StepResult
from app.core.execution_planner import ExecutionPlanner
from app.core.orchestrator import OrchestratorAgent
from app.core.result_aggregator import ResultAggregator


class FakeLLM:
    def __init__(self, accepted=True):
        self.accepted = accepted

    def generate(self, messages, model_options=None):
        return "llm answer"

    def review(self, task_input, final_output):
        return self.accepted


class FakeEngine:
    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    def execute(self, plan):
        self.calls += 1
        if self.results:
            return self.results.pop(0)
        return ExecutionResult("task-1", "succeeded", [StepResult("s1", "succeeded", "ok")], completed_parts=["s1"])


class FakeToolInterface:
    def __init__(self):
        self.intents = []

    def record_intent(self, tool_name, requested_by, input):
        self.intents.append((tool_name, requested_by, input))


class FakeMemoryExtractor:
    def extract(self, task_id, final_output):
        return [{"content": "prefers concise answers", "reason": "stable preference"}]


def make_agent(engine=None, llm=None, tool_interface=None, memory_extractor=None):
    return OrchestratorAgent(
        decision_engine=DecisionEngine(),
        execution_planner=ExecutionPlanner(),
        execution_engine=engine,
        result_aggregator=ResultAggregator(),
        llm_provider=llm or FakeLLM(),
        tool_interface=tool_interface,
        memory_extractor=memory_extractor,
    )


def test_simple_direct_route():
    outcome = make_agent(memory_extractor=FakeMemoryExtractor()).handle("task-1", "What is Python?")

    assert outcome.status == "succeeded"
    assert outcome.mode == "direct"
    assert outcome.result == "llm answer"
    assert outcome.candidate_memories[0].status == "pending"


class FakeSucceededToolInterface:
    def request_tool(self, *, tool_name, requested_by, input, task_id=None):
        class Result:
            execution_status = "succeeded"
            output = {"timezone": input["timezone"], "datetime": "2026-05-30T12:00:00+08:00"}
            error = None
            message = "ok"

        return Result()


def test_tool_intent_route_records_intent_without_downgrade():
    tools = FakeToolInterface()
    outcome = make_agent(tool_interface=tools).handle("task-1", "weather in Shanghai")

    assert outcome.status == "succeeded"
    assert outcome.tool_required is True
    assert "Tool request prepared" in outcome.tool_message
    assert tools.intents[0][0] == "weather_query"


def test_tool_intent_route_can_return_real_tool_result():
    outcome = make_agent(tool_interface=FakeSucceededToolInterface()).handle("task-1", "北京时间几点")

    assert outcome.status == "succeeded"
    assert outcome.tool_required is True
    assert "Asia/Shanghai" in outcome.tool_message


def test_clarification_route():
    outcome = make_agent().handle("task-1", "do it")

    assert outcome.status == "waiting_for_clarification"
    assert outcome.clarification_question


def test_complex_route_uses_planner_engine_aggregator_and_review():
    engine = FakeEngine([ExecutionResult("task-1", "succeeded", [StepResult("s1", "succeeded", "ok")], completed_parts=["s1"])])

    outcome = make_agent(engine=engine).handle("task-1", "First analyze, then write, and finally verify.")

    assert outcome.status == "succeeded"
    assert outcome.mode == "dag"
    assert engine.calls == 1


def test_complex_route_retries_three_times_then_returns_failure():
    failed = ExecutionResult("task-1", "failed", [StepResult("s1", "failed", error="bad")], error="bad", incomplete_parts=["s1"])
    engine = FakeEngine([failed, failed, failed, failed])

    outcome = make_agent(engine=engine, llm=FakeLLM(accepted=False)).handle("task-1", "First analyze, then write, and finally verify.")

    assert outcome.status == "failed"
    assert outcome.failure.retry_count == 3
    assert engine.calls == 4
