from app.core.execution_engine import ExecutionEngine
from app.core.execution_planner import ExecutionPlan, PlanStep


class FakeRuntime:
    def __init__(self):
        self.calls = []

    def invoke(self, capability, description, shared_context):
        self.calls.append((capability, description, shared_context))
        return {"status": "succeeded", "output": f"{capability}:{description}"}


class FakeToolResult:
    def __init__(self, tool_name="web_search", status="succeeded", output=None, message="ok"):
        self.tool_name = tool_name
        self.requested_by = "researcher"
        self.input = {}
        self.permission_status = "allowed"
        self.execution_status = status
        self.message = message
        self.output = output or {"items": ["result"]}
        self.error = None if status == "succeeded" else {"code": "tool_error"}

    def to_record(self):
        return {
            "invocation_id": "tool-invocation-1",
            "task_id": "task-1",
            "tool_name": self.tool_name,
            "input": {"query": "internal query"},
            "permission_status": "allowed",
            "execution_status": self.execution_status,
            "message": self.message,
            "output": self.output,
            "error": self.error,
            "created_at": "2026-01-01T00:00:00Z",
        }


class FakeToolGateway:
    def __init__(self, status="succeeded"):
        self.status = status
        self.calls = []

    def request_tool(self, *, tool_name, requested_by, input, task_id=None):
        self.calls.append((tool_name, requested_by, input, task_id))
        return FakeToolResult(tool_name=tool_name, status=self.status, message="tool failed" if self.status != "succeeded" else "ok")


class DenyingBudget:
    def check_step(self, task_id, step):
        return "budget exhausted"


class TimeoutBudget:
    def check_timeout(self, task_id):
        return "task timed out"


class FakeContext:
    def __init__(self):
        self.results = []

    def add_intermediate_result(self, task_id, step_id, output):
        self.results.append((task_id, step_id, output))


def make_plan(mode, steps):
    return ExecutionPlan(plan_id="plan-1", task_id="task-1", execution_mode=mode, steps=steps)


def test_executes_supervisor_steps_with_fake_runtime():
    runtime = FakeRuntime()
    context = FakeContext()
    plan = make_plan("supervisor", [PlanStep("s1", "one", "analyst"), PlanStep("s2", "two", "writer")])

    result = ExecutionEngine(agent_runtime=runtime, context_manager=context).execute(plan)

    assert result.status == "succeeded"
    assert [item.step_id for item in result.step_results] == ["s1", "s2"]
    assert len(runtime.calls) == 2
    assert len(context.results) == 2


def test_executes_dag_after_dependencies():
    runtime = FakeRuntime()
    plan = make_plan("dag", [PlanStep("s1", "one", "analyst"), PlanStep("s2", "two", "writer", dependencies=["s1"])])

    result = ExecutionEngine(agent_runtime=runtime).execute(plan)

    assert result.status == "succeeded"
    assert runtime.calls[1][2] == {"s1": "analyst:one"}


def test_stops_on_budget_failure():
    plan = make_plan("supervisor", [PlanStep("s1", "one", "analyst")])

    result = ExecutionEngine(budget_manager=DenyingBudget()).execute(plan)

    assert result.status == "budget_exceeded"
    assert result.incomplete_parts == ["s1"]


def test_direct_tool_path_executes_gateway():
    plan = make_plan("direct", [PlanStep("s1", "weather", "tool_user", kind="tool", allowed_tools=["web_search"])])
    gateway = FakeToolGateway()

    result = ExecutionEngine(tool_gateway=gateway).execute(plan)

    assert result.status == "succeeded"
    assert result.step_results[0].status == "succeeded"
    assert gateway.calls[0][0] == "web_search"


def test_complex_step_runs_tool_before_agent_and_passes_context():
    runtime = FakeRuntime()
    gateway = FakeToolGateway()
    plan = make_plan("supervisor", [PlanStep("s1", "search and analyze", "researcher", allowed_tools=["web_search"])])

    result = ExecutionEngine(agent_runtime=runtime, tool_gateway=gateway).execute(plan)

    assert result.status == "succeeded"
    assert gateway.calls
    assert "tool_results" in runtime.calls[0][2]


def test_tool_context_passed_to_agent_excludes_internal_invocation_fields():
    runtime = FakeRuntime()
    gateway = FakeToolGateway()
    plan = make_plan("supervisor", [PlanStep("s1", "search and analyze", "researcher", allowed_tools=["web_search"])])

    result = ExecutionEngine(agent_runtime=runtime, tool_gateway=gateway).execute(plan)

    assert result.status == "succeeded"
    tool_result = runtime.calls[0][2]["tool_results"][0]
    assert "tool_name" in tool_result
    assert "output" in tool_result
    assert "invocation_id" not in tool_result
    assert "task_id" not in tool_result
    assert "input" not in tool_result
    assert "permission_status" not in tool_result
    assert "created_at" not in tool_result


def test_web_search_query_excludes_session_context_and_internal_prompt_text():
    runtime = FakeRuntime()
    gateway = FakeToolGateway()
    plan = make_plan(
        "supervisor",
        [
            PlanStep(
                "s1",
                "Research business model for the original task.\nOriginal task: \u8c03\u7814\u7279\u65af\u62c9\u516c\u53f8",
                "researcher",
                allowed_tools=["web_search"],
            )
        ],
    )

    result = ExecutionEngine(agent_runtime=runtime, tool_gateway=gateway).execute(
        plan,
        session_context="Session context from previous tasks https://duckduckgo.com/html/?q=%E7%89%B9",
    )

    assert result.status == "succeeded"
    query = gateway.calls[0][2]["query"]
    assert "\u8c03\u7814\u7279\u65af\u62c9\u516c\u53f8" in query
    assert "Research business model" in query
    assert "Session context" not in query
    assert "duckduckgo.com" not in query
    assert len(query) <= 260


def test_business_research_query_does_not_force_financial_keywords_for_company_name_only():
    gateway = FakeToolGateway()
    plan = make_plan(
        "supervisor",
        [
            PlanStep(
                "s1",
                "Research business model and products.\nOriginal task: \u8c03\u7814\u7279\u65af\u62c9\u516c\u53f8",
                "researcher",
                allowed_tools=["web_search"],
            )
        ],
    )

    result = ExecutionEngine(agent_runtime=FakeRuntime(), tool_gateway=gateway).execute(plan)

    assert result.status == "succeeded"
    query = gateway.calls[0][2]["query"]
    assert "market capitalization" not in query
    assert "stock price" not in query


def test_complex_step_stops_when_required_tool_fails():
    runtime = FakeRuntime()
    gateway = FakeToolGateway(status="failed")
    plan = make_plan("supervisor", [PlanStep("s1", "search and analyze", "researcher", allowed_tools=["web_search"])])

    result = ExecutionEngine(agent_runtime=runtime, tool_gateway=gateway).execute(plan)

    assert result.status == "failed"
    assert runtime.calls == []
    assert result.step_results[0].status == "failed"


def test_research_step_continues_with_degraded_context_when_search_fails():
    runtime = FakeRuntime()
    gateway = FakeToolGateway(status="failed")
    plan = make_plan(
        "supervisor",
        [PlanStep("s1", "Research history.\nOriginal task: research Tesla", "researcher", allowed_tools=["web_search"])],
    )

    result = ExecutionEngine(agent_runtime=runtime, tool_gateway=gateway).execute(plan)

    assert result.status == "succeeded"
    assert runtime.calls
    tool_result = runtime.calls[0][2]["tool_results"][0]
    assert tool_result["execution_status"] == "failed"
    assert "error" in tool_result


def test_stops_on_timeout_failure():
    plan = make_plan("supervisor", [PlanStep("s1", "one", "analyst")])

    result = ExecutionEngine(budget_manager=TimeoutBudget()).execute(plan)

    assert result.status == "timeout"
    assert result.incomplete_parts == ["s1"]
