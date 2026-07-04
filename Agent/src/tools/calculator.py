"""
计算器工具。支持基本的数学表达式。限制了命名空间防注入。
"""
import math
from tool_registry import ToolSpec, ToolResult, ToolHandler


SPEC = ToolSpec(
    name="calculator",
    description="计算数学表达式。支持加减乘除、幂运算、常用数学函数(sin/cos/sqrt/log等)。",
    parameters={
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "要计算的数学表达式，例如 '2 * (3 + 4)' 或 'sqrt(144)'"
            }
        },
        "required": ["expression"]
    }
)

# 白名单：只允许这些函数和常量
_SAFE_NAMES = {
    "abs": abs, "round": round, "min": min, "max": max,
    "int": int, "float": float,
    "pi": math.pi, "e": math.e,
    "sqrt": math.sqrt, "pow": pow,
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "log": math.log, "log2": math.log2, "log10": math.log10,
    "ceil": math.ceil, "floor": math.floor,
}


def handler(args: dict) -> ToolResult:
    expr = args.get("expression", "").strip()
    if not expr:
        return ToolResult(ok=False, output="", error="表达式不能为空")

    try:
        # 用受限的命名空间执行 eval
        result = eval(expr, {"__builtins__": {}}, _SAFE_NAMES)
        return ToolResult(ok=True, output=str(result))
    except Exception as e:
        return ToolResult(ok=False, output="", error=f"计算失败: {e}")
