"""
handler.py — Calculator function logic.

Pure Python entry point — runs anywhere (Flask backend, CLI, Telegram bot).
"""
from __future__ import annotations

import ast
import operator
from dataclasses import dataclass


_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


@dataclass
class CalcResult:
    expression: str
    result: float
    error: str = ""

    def to_dict(self) -> dict:
        return {"expression": self.expression, "result": self.result, "error": self.error}


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"unsupported constant: {node.value!r}")
    if isinstance(node, ast.BinOp):
        op = _OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"unsupported operator: {type(node.op).__name__}")
        return op(_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp):
        op = _OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"unsupported unary op: {type(node.op).__name__}")
        return op(_safe_eval(node.operand))
    raise ValueError(f"unsupported expression: {type(node).__name__}")


def calculate(expression: str) -> CalcResult:
    """Evaluate a mathematical expression safely."""
    try:
        tree = ast.parse(expression.strip(), mode="eval")
        result = _safe_eval(tree.body)
        return CalcResult(expression=expression, result=float(result))
    except Exception as e:
        return CalcResult(expression=expression, result=0.0, error=str(e))


_history: list[CalcResult] = []


def record(result: CalcResult) -> None:
    _history.append(result)
    if len(_history) > 100:
        _history.pop(0)


def history() -> list[dict]:
    return [r.to_dict() for r in reversed(_history)]


def clear_history() -> None:
    _history.clear()


if __name__ == "__main__":
    import sys
    expr = " ".join(sys.argv[1:]) or "2 + 2"
    res = calculate(expr)
    if res.error:
        print(f"Error: {res.error}")
    else:
        print(f"{res.expression} = {res.result}")
