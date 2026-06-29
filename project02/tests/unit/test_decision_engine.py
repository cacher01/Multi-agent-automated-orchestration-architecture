from app.core.decision_engine import DecisionEngine


class FakeLogger:
    def __init__(self):
        self.events = []

    def log(self, task_id, event_type, payload):
        self.events.append((task_id, event_type, payload))


class FakeRoutingLLM:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def generate(self, messages, model_options=None):
        self.calls.append((messages, model_options))

        class Response:
            content = self.content

        return Response()


def test_simple_direct_task():
    logger = FakeLogger()
    result = DecisionEngine(logger=logger).decide("What is Python?", "task-1")

    assert result.complexity == "simple"
    assert result.execution_mode == "direct"
    assert result.requires_tools is False
    assert result.requires_clarification is False
    assert logger.events[-1][1] == "decision_made"


def test_simple_explanation_does_not_call_tool_even_with_llm_available():
    llm = FakeRoutingLLM(
        '{"complexity":"complex","execution_mode":"supervisor","requires_tools":true,'
        '"requires_clarification":false,"required_capabilities":["researcher"],"reason":"bad route",'
        '"tool_name":"web_search","clarification_question":null}'
    )

    result = DecisionEngine(llm_provider=llm).decide("\u8bf7\u7b80\u5355\u4ecb\u7ecd\u4e00\u4e0bPython")

    assert result.complexity == "simple"
    assert result.execution_mode == "direct"
    assert result.requires_tools is False
    assert result.tool_name is None
    assert llm.calls == []


def test_general_company_explanation_without_freshness_stays_direct():
    result = DecisionEngine().decide("\u8bf7\u8bf4\u660e\u82f9\u679c\u516c\u53f8\u7684\u5546\u4e1a\u6a21\u5f0f")

    assert result.complexity == "simple"
    assert result.execution_mode == "direct"
    assert result.requires_tools is False
    assert result.tool_name is None


def test_llm_decision_is_used_for_unseen_routing_task():
    llm = FakeRoutingLLM(
        """
        ```json
        {
          "complexity": "complex",
          "execution_mode": "supervisor",
          "requires_tools": true,
          "requires_clarification": false,
          "required_capabilities": ["researcher", "analyst", "writer"],
          "reason": "Needs external facts and synthesis.",
          "tool_name": "web_search",
          "clarification_question": null
        }
        ```
        """
    )

    result = DecisionEngine(llm_provider=llm).decide("Assess three semiconductor suppliers using current supply chain news.")

    assert result.complexity == "complex"
    assert result.execution_mode == "supervisor"
    assert result.requires_tools is True
    assert result.tool_name == "web_search"
    assert llm.calls


def test_llm_tool_decision_defaults_to_search_when_tool_name_missing():
    llm = FakeRoutingLLM(
        '{"complexity":"complex","execution_mode":"supervisor","requires_tools":true,'
        '"requires_clarification":false,"required_capabilities":[],"reason":"needs external data",'
        '"tool_name":null,"clarification_question":null}'
    )

    result = DecisionEngine(llm_provider=llm).decide("Research current competitors and summarize risks.")

    assert result.requires_tools is True
    assert result.tool_name == "web_search"
    assert result.required_capabilities == ["researcher"]


def test_llm_direct_tool_decision_is_upgraded_for_complex_analysis():
    llm = FakeRoutingLLM(
        '{"complexity":"simple","execution_mode":"direct","requires_tools":true,'
        '"requires_clarification":false,"required_capabilities":["researcher"],"reason":"search needed",'
        '"tool_name":"web_search","clarification_question":null}'
    )

    result = DecisionEngine(llm_provider=llm).decide("调查三家主流云服务公司的最新AI基础设施投入，并给出风险对比")

    assert result.complexity == "complex"
    assert result.execution_mode != "direct"
    assert result.requires_tools is True


def test_weather_style_tool_intent_stays_direct():
    result = DecisionEngine().decide("What is the weather in Shanghai today?", "task-1")

    assert result.complexity == "simple"
    assert result.execution_mode == "direct"
    assert result.requires_tools is True
    assert result.tool_name == "weather_query"
    assert result.required_capabilities == ["tool_user"]


def test_chinese_current_time_uses_time_tool_not_web_search():
    result = DecisionEngine().decide("\u73b0\u5728\u51e0\u70b9", "task-1")

    assert result.complexity == "simple"
    assert result.execution_mode == "direct"
    assert result.requires_tools is True
    assert result.tool_name == "time_lookup"


def test_company_research_requires_search_and_multi_agent_orchestration():
    result = DecisionEngine().decide("\u8c03\u7814\u7279\u65af\u62c9\u516c\u53f8", "task-1")

    assert result.complexity == "complex"
    assert result.execution_mode != "direct"
    assert result.requires_tools is True
    assert result.tool_name == "web_search"
    assert "researcher" in result.required_capabilities
    assert "writer" in result.required_capabilities


def test_company_research_guard_overrides_bad_llm_direct_route():
    llm = FakeRoutingLLM(
        '{"complexity":"simple","execution_mode":"direct","requires_tools":false,'
        '"requires_clarification":false,"required_capabilities":[],"reason":"bad route",'
        '"tool_name":null,"clarification_question":null}'
    )

    result = DecisionEngine(llm_provider=llm).decide("\u8c03\u7814\u7279\u65af\u62c9\u516c\u53f8", "task-1")

    assert result.complexity == "complex"
    assert result.execution_mode == "supervisor"
    assert result.requires_tools is True
    assert result.tool_name == "web_search"
    assert llm.calls == []


def test_chinese_weather_and_time_tool_intents_stay_direct():
    weather = DecisionEngine().decide("查询上海天气", "task-1")
    time = DecisionEngine().decide("北京时间几点", "task-2")

    assert weather.execution_mode == "direct"
    assert weather.requires_tools is True
    assert weather.tool_name == "weather_query"
    assert time.execution_mode == "direct"
    assert time.requires_tools is True
    assert time.tool_name == "time_lookup"


def test_chinese_file_reader_intent_detects_filename():
    result = DecisionEngine().decide("请读取 README.md", "task-1")

    assert result.execution_mode == "direct"
    assert result.requires_tools is True
    assert result.tool_name == "file_reader"


def test_complex_chinese_search_and_analysis_uses_researcher_tool():
    result = DecisionEngine().decide("请搜索今天AI新闻并分析对开发者的影响", "task-1")

    assert result.complexity == "complex"
    assert result.execution_mode == "supervisor"
    assert result.requires_tools is True
    assert result.tool_name == "web_search"
    assert result.required_capabilities[0] == "researcher"


def test_financial_market_cap_report_requires_research_tool():
    result = DecisionEngine().decide("调查特斯拉、英伟达、苹果三家公司在2025年底的市值，并写一份投资分析报告")

    assert result.complexity == "complex"
    assert result.requires_tools is True
    assert result.tool_name == "web_search"
    assert result.required_capabilities[0] == "researcher"


def test_general_chinese_research_compare_task_requires_orchestration_and_search():
    result = DecisionEngine().decide("调查三家主流云服务公司的最新AI基础设施投入，并给出风险对比")

    assert result.complexity == "complex"
    assert result.execution_mode == "discussion"
    assert result.requires_tools is True
    assert result.tool_name == "web_search"


def test_complex_task_detection():
    result = DecisionEngine().decide("First analyze the options, then implement a plan, and finally verify it.")

    assert result.complexity == "complex"
    assert result.execution_mode == "dag"
    assert "analyst" in result.required_capabilities


def test_chinese_complex_task_detection():
    result = DecisionEngine().decide("先分析方案，然后设计实现步骤，最后验证结果。")

    assert result.complexity == "complex"
    assert result.execution_mode == "dag"


def test_chinese_planning_task_uses_dag_mode():
    result = DecisionEngine().decide("请帮我设计一个个人学习Python的三天计划，包括每天目标、练习内容和验收标准。")

    assert result.complexity == "complex"
    assert result.execution_mode == "dag"


def test_clarification_needed_task():
    result = DecisionEngine().decide("do it")

    assert result.requires_clarification is True
    assert result.clarification_question


def test_short_normal_question_does_not_force_clarification():
    result = DecisionEngine().decide("你好")

    assert result.requires_clarification is False
    assert result.execution_mode == "direct"
