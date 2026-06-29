"""Rule-first task routing decisions for the orchestrator."""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class DecisionResult:
    complexity: str
    execution_mode: str
    requires_tools: bool = False
    requires_clarification: bool = False
    required_capabilities: list[str] = field(default_factory=list)
    reason: str = ""
    tool_name: str | None = None
    clarification_question: str | None = None


class LLMDecisionProvider(Protocol):
    def generate(self, messages: list[dict[str, str]], model_options: dict[str, Any] | None = None) -> Any:
        ...


class DecisionEngine:
    """Classifies user tasks with rules first and LLM assistance only when needed."""

    _tool_patterns: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("web_search", ("search", "look up", "find online", "google", "搜索", "联网查找", "网上查找")),
        ("web_fetch", ("fetch url", "read url", "open url", "https://", "http://", "打开网址", "读取网址")),
        ("weather_query", ("weather", "forecast", "temperature", "天气", "气温", "温度", "天气预报")),
        ("time_lookup", ("current time", "time zone", "timezone", "what time", "几点", "时间", "当前时间", "现在时间")),
        ("calculator", ("calculate", "calculator", "convert unit", "unit conversion", "计算", "算一下", "换算")),
        ("file_reader", ("read file", "open file", "读取文件", "打开文件")),
        ("file_writer", ("write file", "save file", "create file", "写入文件", "保存文件", "创建文件")),
        ("code_executor", ("run code", "execute code", "运行代码", "执行代码")),
        ("database_query", ("query database", "sql", "查询数据库")),
        ("api_caller", ("call api", "request api", "调用api", "请求api")),
    )
    _preferred_tool_patterns: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("web_fetch", ("fetch url", "read url", "open url", "https://", "http://", "打开网址", "读取网址")),
        ("weather_query", ("weather", "forecast", "temperature", "天气", "气温", "温度", "天气预报")),
        ("time_lookup", ("current time", "time zone", "timezone", "what time", "几点", "时间", "当前时间", "现在时间")),
        ("calculator", ("calculate", "calculator", "convert unit", "unit conversion", "计算", "算一下", "换算")),
        ("file_reader", ("read file", "open file", "读取文件", "打开文件", "查看文件", "读取 ", "查看 ")),
        ("file_writer", ("write file", "save file", "create file", "写入文件", "保存文件", "创建文件")),
        ("code_executor", ("run code", "execute code", "运行代码", "执行代码")),
        ("database_query", ("query database", "sql", "查询数据库")),
        ("api_caller", ("call api", "request api", "调用api", "请求api")),
        ("web_search", ("search", "look up", "find online", "google", "搜索", "查找", "联网查询", "网上查找", "最新", "新闻", "资料")),
    )
    _complex_markers = (
        " first ",
        " then ",
        " finally ",
        "compare",
        "design",
        "implement",
        "verify",
        "evaluate",
        "analyze",
        "plan",
        "build",
        "debate",
        "proposal",
        "strategy",
        "roadmap",
        "requirements",
        "architecture",
        "report",
        "先",
        "然后",
        "最后",
        "比较",
        "设计",
        "实现",
        "验证",
        "分析",
        "计划",
        "规划",
        "制定",
        "方案",
        "步骤",
        "需求",
        "架构",
        "文档",
        "报告",
        "优化",
        "调研",
        "构建",
        "讨论",
    )
    _unclear_inputs = {"help", "do it", "handle this", "fix it"}
    _finance_markers = (
        "\u5e02\u503c",
        "\u80a1\u4ef7",
        "\u6295\u8d44",
        "\u8d22\u62a5",
        "\u4f30\u503c",
        "\u516c\u53f8",
        "\u80a1\u7968",
        "\u7279\u65af\u62c9",
        "\u82f1\u4f1f\u8fbe",
        "\u82f9\u679c",
        "market cap",
        "market capitalization",
        "stock price",
        "investment",
        "valuation",
        "earnings",
        "tesla",
        "nvidia",
        "apple",
    )
    _external_data_markers = (
        "\u6700\u65b0",
        "\u5f53\u524d",
        "\u4eca\u5929",
        "\u8c03\u67e5",
        "\u8c03\u7814",
        "\u7814\u7a76",
        "\u68c0\u7d22",
        "\u641c\u7d22",
        "\u65b0\u95fb",
        "\u5e02\u573a",
        "\u516c\u53f8",
        "\u4ea7\u54c1",
        "\u4ef7\u683c",
        "\u6295\u5165",
        "\u6570\u636e",
        "current",
        "latest",
        "recent",
        "research",
        "investigate",
        "market",
        "news",
    )
    _semantic_complex_markers = (
        "\u8c03\u67e5",
        "\u8c03\u7814",
        "\u7814\u7a76",
        "\u5206\u6790",
        "\u62a5\u544a",
        "\u5bf9\u6bd4",
        "\u6bd4\u8f83",
        "\u8bc4\u4f30",
        "\u98ce\u9669",
        "\u65b9\u6848",
        "\u7b56\u7565",
        "\u603b\u7ed3",
        "\u89c4\u5212",
        "\u8bbe\u8ba1",
        "\u5efa\u8bae",
        "analyze",
        "analysis",
        "report",
        "compare",
        "evaluate",
        "risk",
        "strategy",
    )
    _preferred_complex_markers = (
        "先",
        "然后",
        "最后",
        "比较",
        "设计",
        "实现",
        "验证",
        "分析",
        "计划",
        "规划",
        "制定",
        "方案",
        "步骤",
        "需求",
        "架构",
        "文档",
        "报告",
        "优化",
        "调研",
        "构建",
        "讨论",
        "影响",
    )

    def __init__(
        self,
        llm_provider: LLMDecisionProvider | None = None,
        logger: Any | None = None,
        llm_timeout_seconds: float = 8.0,
    ) -> None:
        self.llm_provider = llm_provider
        self.logger = logger
        self.llm_timeout_seconds = llm_timeout_seconds

    def decide(self, task_input: str, task_id: str | None = None) -> DecisionResult:
        text = (task_input or "").strip()
        lowered = f" {text.lower()} "

        if not text:
            return self._log(
                task_id,
                DecisionResult(
                    complexity="simple",
                    execution_mode="direct",
                    requires_clarification=True,
                    reason="Task input is empty.",
                    clarification_question="Please provide the task goal and any key constraints.",
                ),
            )

        if self._is_simple_explanation_request(lowered):
            return self._log(
                task_id,
                DecisionResult(
                    complexity="simple",
                    execution_mode="direct",
                    reason="Detected a simple explanation task that does not require external tools.",
                ),
            )

        if self._is_research_profile_request(lowered):
            return self._log(
                task_id,
                DecisionResult(
                    complexity="complex",
                    execution_mode="supervisor",
                    requires_tools=True,
                    required_capabilities=["researcher", "analyst", "writer", "reviewer"],
                    reason="Detected a research task that should use the dedicated supervisor research profile.",
                    tool_name="web_search",
                ),
            )

        llm_decision = self._optional_llm_decision(text, task_id)
        if llm_decision is not None:
            return self._log(task_id, llm_decision)

        tool_name = self._detect_tool(lowered)
        if tool_name is None and self._is_unclear(text):
            return self._log(
                task_id,
                DecisionResult(
                    complexity="simple",
                    execution_mode="direct",
                    requires_clarification=True,
                    reason="Task lacks an actionable object.",
                    clarification_question="Please provide the task goal and any key constraints.",
                ),
            )

        if tool_name and self._is_single_tool_intent(lowered):
            return self._log(
                task_id,
                DecisionResult(
                    complexity="simple",
                    execution_mode="direct",
                    requires_tools=True,
                    required_capabilities=[self._primary_capability_for(tool_name)],
                    reason=f"Detected a single simple tool intent for {tool_name}.",
                    tool_name=tool_name,
                ),
            )

        if self._is_complex(lowered):
            return self._log(
                task_id,
                DecisionResult(
                    complexity="complex",
                    execution_mode=self._select_complex_mode(lowered),
                    requires_tools=bool(tool_name),
                    required_capabilities=self._capabilities_for(lowered, tool_name),
                    reason="Detected multi-step, multi-goal, or planning-heavy task.",
                    tool_name=tool_name,
                ),
            )

        return self._log(
            task_id,
            DecisionResult(
                complexity="simple",
                execution_mode="direct",
                reason="Rule-based classifier identified a simple direct task.",
            ),
        )

    def _is_unclear(self, text: str) -> bool:
        lowered = text.lower().strip()
        if not lowered:
            return True
        return lowered in self._unclear_inputs

    def _detect_tool(self, lowered: str) -> str | None:
        for tool_name, markers in self._preferred_tool_patterns:
            if tool_name != "web_search" and any(marker in lowered for marker in markers):
                return tool_name
        if self._needs_financial_external_data(lowered):
            return "web_search"
        if self._needs_external_search(lowered):
            return "web_search"
        for tool_name, markers in self._preferred_tool_patterns:
            if any(marker in lowered for marker in markers):
                return tool_name
        for tool_name, markers in self._tool_patterns:
            if any(marker in lowered for marker in markers):
                return tool_name
        return None

    def _is_simple_explanation_request(self, lowered: str) -> bool:
        if self._has_explicit_tool_request(lowered) or self._needs_external_search(lowered) or self._needs_financial_external_data(lowered):
            return False
        simple_markers = (
            "\u4ecb\u7ecd",
            "\u7b80\u5355\u4ecb\u7ecd",
            "\u8bf4\u660e",
            "\u89e3\u91ca",
            "\u4ec0\u4e48\u662f",
            "\u662f\u4ec0\u4e48",
            "what is",
            "explain",
            "introduce",
            "describe",
        )
        return any(marker in lowered for marker in simple_markers)

    def _has_explicit_tool_request(self, lowered: str) -> bool:
        return any(marker in lowered for _, markers in self._preferred_tool_patterns for marker in markers)

    def _needs_external_search(self, lowered: str) -> bool:
        freshness_markers = (
            "\u6700\u65b0",
            "\u5f53\u524d",
            "\u4eca\u5929",
            "\u73b0\u5728",
            "\u65b0\u95fb",
            "\u68c0\u7d22",
            "\u641c\u7d22",
            "\u67e5\u627e",
            "\u8054\u7f51",
            "current",
            "latest",
            "recent",
            "news",
            "search",
            "look up",
            "find online",
        )
        if any(marker in lowered for marker in freshness_markers):
            return True
        research_markers = ("\u8c03\u67e5", "\u8c03\u7814", "\u7814\u7a76", "research", "investigate")
        data_markers = (
            "\u5e02\u573a",
            "\u6570\u636e",
            "\u6295\u5165",
            "\u8d44\u6599",
            "\u516c\u53f8",
            "\u4f01\u4e1a",
            "\u4e1a\u52a1",
            "\u8d22\u52a1",
            "\u98ce\u9669",
            "\u7279\u65af\u62c9",
            "\u82f1\u4f1f\u8fbe",
            "\u82f9\u679c",
            "market",
            "data",
            "company",
            "business",
            "financial",
            "risk",
            "tesla",
            "nvidia",
            "apple",
        )
        return any(marker in lowered for marker in research_markers) and any(marker in lowered for marker in data_markers)

    def _needs_financial_external_data(self, lowered: str) -> bool:
        financial_intent = (
            "\u5e02\u503c",
            "\u80a1\u4ef7",
            "\u6295\u8d44",
            "\u8d22\u62a5",
            "\u4f30\u503c",
            "\u80a1\u7968",
            "market cap",
            "market capitalization",
            "stock price",
            "investment",
            "valuation",
            "earnings",
        )
        entity_markers = ("\u7279\u65af\u62c9", "\u82f1\u4f1f\u8fbe", "\u82f9\u679c", "tesla", "nvidia", "apple")
        return any(marker in lowered for marker in financial_intent) or (
            any(marker in lowered for marker in entity_markers)
            and any(marker in lowered for marker in ("\u5206\u6790", "\u62a5\u544a", "\u5bf9\u6bd4", "analysis", "report", "compare"))
        )

    def _is_research_profile_request(self, lowered: str) -> bool:
        if any(marker in lowered for marker in ("\u5bf9\u6bd4", "\u6bd4\u8f83", "compare", "comparison")):
            return False
        research_markers = ("\u8c03\u7814", "\u8c03\u67e5", "\u7814\u7a76", "research", "investigate")
        target_markers = (
            "\u516c\u53f8",
            "\u4f01\u4e1a",
            "\u884c\u4e1a",
            "\u5e02\u573a",
            "\u7279\u65af\u62c9",
            "\u82f1\u4f1f\u8fbe",
            "\u82f9\u679c",
            "company",
            "business",
            "market",
            "tesla",
            "nvidia",
            "apple",
        )
        return any(marker in lowered for marker in research_markers) and any(
            marker in lowered for marker in target_markers
        )

    def _is_single_tool_intent(self, lowered: str) -> bool:
        has_complex_marker = any(marker in lowered for marker in self._complex_markers) or any(
            marker in lowered for marker in self._preferred_complex_markers
        ) or any(
            marker in lowered for marker in self._semantic_complex_markers
        )
        return not has_complex_marker and lowered.count(" and ") <= 1

    def _is_complex(self, lowered: str) -> bool:
        if any(marker in lowered for marker in self._semantic_complex_markers):
            return True
        if any(marker in lowered for marker in self._finance_markers) and any(
            marker in lowered for marker in ("\u62a5\u544a", "\u5206\u6790", "\u8c03\u67e5", "\u6bd4\u8f83", "report", "analysis", "compare")
        ):
            return True
        if any(marker in lowered for marker in self._preferred_complex_markers):
            return True
        if any(marker in lowered for marker in self._complex_markers):
            return True
        return (
            lowered.count(" and ") >= 2
            or lowered.count(".") >= 2
            or lowered.count("，") >= 2
            or lowered.count("、") >= 2
            or len(lowered.split()) > 40
            or len(lowered.strip()) >= 80
        )

    def _select_complex_mode(self, lowered: str) -> str:
        if "handoff" in lowered or "transfer" in lowered:
            return "handoff"
        if any(marker in lowered for marker in ("\u5bf9\u6bd4", "\u6bd4\u8f83", "\u8ba8\u8bba")):
            return "discussion"
        if any(marker in lowered for marker in ("\u5148", "\u7136\u540e", "\u6700\u540e", "\u8ba1\u5212", "\u89c4\u5212", "\u6b65\u9aa4")):
            return "dag"
        if any(marker in lowered for marker in ("比较", "讨论")):
            return "discussion"
        if any(marker in lowered for marker in ("先", "然后", "最后", "计划", "规划", "步骤")):
            return "dag"
        if "compare" in lowered or "debate" in lowered or "比较" in lowered or "讨论" in lowered:
            return "discussion"
        if any(marker in lowered for marker in (" first ", " then ", " finally ", "roadmap", "先", "然后", "最后", "计划", "规划", "步骤")):
            return "dag"
        return "supervisor"

    def _capabilities_for(self, lowered: str, tool_name: str | None) -> list[str]:
        capabilities = ["analyst", "writer"]
        if tool_name:
            capabilities.insert(0, self._primary_capability_for(tool_name))
        if any(marker in lowered for marker in ("\u8bc4\u4f30", "\u98ce\u9669", "\u9a8c\u8bc1", "\u5ba1\u6838")):
            capabilities.append("reviewer")
        if any(marker in lowered for marker in ("\u8ba1\u5212", "\u89c4\u5212", "\u8bbe\u8ba1", "\u65b9\u6848")):
            capabilities.insert(0, "planner")
        if "review" in lowered or "verify" in lowered or "验证" in lowered:
            capabilities.append("reviewer")
        if "plan" in lowered or "design" in lowered or "计划" in lowered or "设计" in lowered:
            capabilities.insert(0, "planner")
        return list(dict.fromkeys(capabilities))

    def _primary_capability_for(self, tool_name: str) -> str:
        if tool_name in {"web_search", "web_fetch", "api_caller"}:
            return "researcher"
        return "tool_user"

    def _optional_llm_decision(self, task_input: str, task_id: str | None) -> DecisionResult | None:
        if self.llm_provider is None or self._is_trivial_direct(task_input):
            return None
        prompt = (
            "You are the routing brain of a multi-agent orchestration framework. "
            "Classify the user's task as strict JSON only. "
            "Choose complexity from simple, moderate, complex. "
            "Choose execution_mode from direct, supervisor, dag, discussion, handoff. "
            "Set requires_tools=true when the task needs current facts, external data, files, code execution, calculation, weather, time, API calls, or database access. "
            "Choose one tool_name from web_search, web_fetch, weather_query, time_lookup, calculator, file_reader, file_writer, code_executor, database_query, api_caller, or null. "
            "Choose required_capabilities from planner, researcher, analyst, explorer, writer, reviewer, tool_user. "
            "Use direct only for simple chat, simple reasoning, or one simple tool call. "
            "Use supervisor/dag/discussion/handoff for multi-step tasks. "
            "Return keys: complexity, execution_mode, requires_tools, requires_clarification, required_capabilities, reason, tool_name, clarification_question."
        )
        try:
            response = self._generate_decision(
                [{"role": "system", "content": prompt}, {"role": "user", "content": task_input}],
                {"temperature": 0, "max_tokens": 400},
            )
            content = getattr(response, "content", response)
            data = json.loads(self._extract_json(content)) if isinstance(content, str) else content
            if not isinstance(data, dict):
                return None
            complexity = data.get("complexity")
            execution_mode = data.get("execution_mode")
            if complexity not in {"simple", "moderate", "complex"} or execution_mode not in {
                "direct",
                "supervisor",
                "dag",
                "discussion",
                "handoff",
            }:
                return None
            lowered = f" {task_input.lower()} "
            tool_name = data.get("tool_name") or self._detect_tool(lowered)
            requires_tools = bool(data.get("requires_tools", False) or tool_name)
            capabilities = list(data.get("required_capabilities") or [])
            if requires_tools and tool_name is None:
                tool_name = "web_search"
            if requires_tools and not capabilities and tool_name is not None:
                capabilities = [self._primary_capability_for(tool_name)]
            if self._is_complex(lowered) and execution_mode == "direct":
                complexity = "complex"
                execution_mode = self._select_complex_mode(lowered)
                capabilities = self._capabilities_for(lowered, tool_name)
            return DecisionResult(
                complexity=complexity,
                execution_mode=execution_mode,
                requires_tools=requires_tools,
                requires_clarification=bool(data.get("requires_clarification", False)),
                required_capabilities=capabilities,
                reason=str(data.get("reason") or "LLM-assisted decision."),
                tool_name=tool_name,
                clarification_question=data.get("clarification_question"),
            )
        except Exception as exc:  # LLM assistance must not block rule fallback.
            self._emit_log(task_id, "decision_llm_failed", {"error": str(exc)})
            return None

    def _generate_decision(self, messages: list[dict[str, str]], model_options: dict[str, Any]) -> Any:
        if self.llm_provider is None:
            return None
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self.llm_provider.generate, messages, model_options)
        try:
            return future.result(timeout=self.llm_timeout_seconds)
        except FutureTimeoutError as exc:
            future.cancel()
            raise TimeoutError(f"Decision LLM call exceeded {self.llm_timeout_seconds:.0f} seconds.") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _needs_llm_decision(self, task_input: str) -> bool:
        lowered = task_input.lower()
        if len(task_input) >= 120:
            return True
        return any(marker in lowered for marker in ("unclear", "ambiguous", "不清楚", "不确定", "复杂"))

    def _extract_json(self, content: str) -> str:
        text = content.strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
        if fenced:
            return fenced.group(1)
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1]
        return text

    def _is_trivial_direct(self, task_input: str) -> bool:
        lowered = task_input.lower().strip()
        return lowered in {"hi", "hello", "hey", "你好", "您好", "谢谢", "thanks", "thank you"} or len(lowered) <= 2

    def _log(self, task_id: str | None, decision: DecisionResult) -> DecisionResult:
        self._emit_log(
            task_id,
            "decision_made",
            {
                "complexity": decision.complexity,
                "execution_mode": decision.execution_mode,
                "requires_tools": decision.requires_tools,
                "requires_clarification": decision.requires_clarification,
                "required_capabilities": decision.required_capabilities,
                "tool_name": decision.tool_name,
                "reason": decision.reason,
            },
        )
        return decision

    def _emit_log(self, task_id: str | None, event_type: str, payload: dict[str, Any]) -> None:
        if self.logger is None:
            return
        if hasattr(self.logger, "log_event"):
            self.logger.log_event(task_id or "", event_type, payload)
        elif hasattr(self.logger, "log"):
            self.logger.log(task_id, event_type, payload)
        elif hasattr(self.logger, "record"):
            self.logger.record(task_id, event_type, payload)
