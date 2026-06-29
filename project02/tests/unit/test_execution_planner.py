from app.core.decision_engine import DecisionResult
from app.core.execution_planner import ExecutionPlanner


class FakeStorage:
    def __init__(self):
        self.saved = []

    def save_execution_plan(self, plan):
        self.saved.append(plan)


def test_direct_mode_plan():
    plan = ExecutionPlanner().create_plan("task-1", "Say hi", DecisionResult("simple", "direct"))

    assert plan.execution_mode == "direct"
    assert plan.steps[0].kind == "direct"


def test_supervisor_mode_plan():
    decision = DecisionResult("complex", "supervisor", required_capabilities=["analyst", "writer"])
    plan = ExecutionPlanner().create_plan("task-1", "Analyze and write", decision)

    assert [step.capability for step in plan.steps] == ["analyst", "writer"]
    assert not plan.dependencies


def test_supervisor_research_plan_uses_multiple_tool_backed_research_angles():
    decision = DecisionResult(
        "complex",
        "supervisor",
        requires_tools=True,
        required_capabilities=["researcher", "analyst", "writer", "reviewer"],
        tool_name="web_search",
    )
    plan = ExecutionPlanner().create_plan("task-1", "\u8c03\u7814\u7279\u65af\u62c9\u516c\u53f8", decision)

    research_steps = [step for step in plan.steps if step.capability == "researcher"]
    assert len(plan.steps) <= plan.budget["max_child_agents_per_task"]
    assert len(research_steps) == 3
    assert all(step.allowed_tools == ["web_search"] for step in research_steps)
    assert any("history" in step.description.lower() for step in research_steps)
    assert any("business" in step.description.lower() for step in research_steps)
    assert any("technology" in step.description.lower() for step in research_steps)
    assert plan.steps[-2].capability == "writer"
    assert plan.steps[-1].capability == "reviewer"


def test_dag_mode_plan():
    plan = ExecutionPlanner().create_plan("task-1", "First analyze then write", DecisionResult("complex", "dag"))

    assert [step.capability for step in plan.steps] == ["planner", "analyst", "writer", "reviewer"]
    assert plan.steps[1].dependencies == ["step-1"]
    assert plan.dependencies["step-2"] == ["step-1"]


def test_discussion_mode_plan():
    plan = ExecutionPlanner().create_plan("task-1", "Compare options", DecisionResult("complex", "discussion"))

    assert len(plan.steps) == 4
    assert plan.steps[1].dependencies == ["step-1"]
    assert plan.steps[-1].dependencies == ["step-3"]


def test_handoff_mode_plan():
    plan = ExecutionPlanner().create_plan("task-1", "handoff task", DecisionResult("complex", "handoff"))

    assert plan.steps[1].dependencies == ["step-1"]


def test_clarification_plan_is_not_full_execution_plan():
    decision = DecisionResult("simple", "direct", requires_clarification=True, clarification_question="Need target?")
    plan = ExecutionPlanner().create_plan("task-1", "fix it", decision)

    assert plan.requires_clarification is True
    assert plan.steps == []
    assert plan.clarification_question == "Need target?"


def test_plan_attaches_tools_budget_timeout_and_persists():
    storage = FakeStorage()
    decision = DecisionResult("simple", "direct", requires_tools=True, required_capabilities=["tool_user"], tool_name="web_search")
    plan = ExecutionPlanner(storage=storage, default_timeout=123).create_plan("task-1", "weather", decision)

    assert plan.allowed_tools == ["web_search"]
    assert plan.budget["task_token_budget"] == 12000
    assert plan.timeout == 123
    assert storage.saved == [plan]


def test_discussion_plan_attaches_tools_to_research_step():
    planner = ExecutionPlanner()
    decision = DecisionResult(
        "complex",
        "discussion",
        requires_tools=True,
        required_capabilities=["researcher", "analyst", "writer"],
        tool_name="web_search",
    )

    plan = planner.create_plan("task-1", "research and compare current vendors", decision)

    assert plan.steps[0].capability == "researcher"
    assert plan.steps[0].allowed_tools == ["web_search"]


def test_dag_plan_with_tools_starts_with_research_step():
    planner = ExecutionPlanner()
    decision = DecisionResult(
        "complex",
        "dag",
        requires_tools=True,
        required_capabilities=["researcher", "analyst", "writer"],
        tool_name="web_search",
    )

    plan = planner.create_plan("task-1", "research current data then write report", decision)

    assert plan.steps[0].capability == "researcher"
    assert plan.steps[0].allowed_tools == ["web_search"]
    assert plan.steps[1].dependencies == ["step-1"]
