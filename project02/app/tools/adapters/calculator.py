from __future__ import annotations

import ast
import operator
from collections.abc import Mapping
from typing import Any

from app.tools.adapters.base import AdapterResult, ToolAdapterError

_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


class CalculatorAdapter:
    name = "calculator"

    def execute(self, tool_input: Mapping[str, Any]) -> AdapterResult:
        expression = str(tool_input.get("expression") or "").strip()
        if not expression:
            raise ToolAdapterError("invalid_input", "Calculator expression is required.")
        try:
            tree = ast.parse(expression, mode="eval")
            result = self._evaluate(tree.body)
        except ToolAdapterError:
            raise
        except Exception as exc:
            raise ToolAdapterError("invalid_expression", "Calculator expression could not be evaluated.") from exc
        return AdapterResult(
            output={"result": str(result), "steps": [expression]},
            message="Calculation completed.",
        )

    def _evaluate(self, node: ast.AST) -> float | int:
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
            return node.value
        if isinstance(node, ast.BinOp):
            operator_fn: Any = _BINARY_OPERATORS.get(type(node.op))
            if operator_fn is None:
                raise ToolAdapterError("unsupported_operator", "Calculator operator is not supported.")
            return operator_fn(self._evaluate(node.left), self._evaluate(node.right))
        if isinstance(node, ast.UnaryOp):
            unary_operator_fn: Any = _UNARY_OPERATORS.get(type(node.op))
            if unary_operator_fn is None:
                raise ToolAdapterError("unsupported_operator", "Calculator unary operator is not supported.")
            return unary_operator_fn(self._evaluate(node.operand))
        raise ToolAdapterError("unsafe_expression", "Calculator only supports numeric arithmetic expressions.")
