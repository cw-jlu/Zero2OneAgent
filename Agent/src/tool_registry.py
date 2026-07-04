"""
工具注册与执行。
- 每个工具有 name / description / parameters schema
- 统一注册到 ToolRegistry，LLM 基于 schema 决定调用
- execute 方法负责路由到对应 handler 并返回结果
不搞太抽象的类继承，一个 dataclass + handler function 就够了。
工具写在 tools/ 目录下面，然后在这里注册。
"""
from __future__ import annotations

import json
import time
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("agent.tools")


@dataclass(frozen=True)
class ToolSpec:
    """工具的静态描述，会被转成 OpenAI function calling 的 schema 发给 LLM"""
    name: str
    description: str
    parameters: dict[str, Any]   # JSON Schema 格式


@dataclass
class ToolResult:
    """工具执行结果"""
    ok: bool
    output: str                  # 返回给 LLM 的文本
    error: str = ""
    elapsed: float = 0.0         # 执行耗时，用于 trace


# handler 签名：接收参数 dict，返回 ToolResult
ToolHandler = Callable[[dict[str, Any]], ToolResult]


@dataclass
class ToolRegistry:
    """
    工具注册表。
    
    用法：
        registry = ToolRegistry()
        registry.register(spec, handler)
        result = registry.execute("calculator", {"expression": "1+1"})
    """
    _specs: dict[str, ToolSpec] = field(default_factory=dict)
    _handlers: dict[str, ToolHandler] = field(default_factory=dict)
    # 执行日志，每次 execute 都记一条
    _trace: list[dict] = field(default_factory=list)

    def register(self, spec: ToolSpec, handler: ToolHandler) -> None:
        """注册一个工具"""
        if spec.name in self._specs:
            logger.warning(f"工具 '{spec.name}' 重复注册，后者覆盖前者")
        self._specs[spec.name] = spec
        self._handlers[spec.name] = handler
        logger.info(f"注册工具: {spec.name}")

    def get_tools_for_llm(self) -> list[dict]:
        """
        生成 OpenAI function calling 格式的 tools 列表。
        这个直接丢给 LLM API 的 tools 参数。
        """
        tools = []
        for name, spec in self._specs.items():
            tools.append({
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                }
            })
        return tools

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        """
        执行工具，记录 trace。
        上层 loop 拿到 LLM 的 tool_calls 后调这个。
        """
        start = time.time()

        if tool_name not in self._handlers:
            result = ToolResult(
                ok=False,
                output="",
                error=f"未知工具: {tool_name}，可用工具: {list(self._specs.keys())}",
            )
        else:
            try:
                result = self._handlers[tool_name](arguments)
                result.elapsed = time.time() - start
            except Exception as e:
                result = ToolResult(
                    ok=False,
                    output="",
                    error=f"工具 '{tool_name}' 执行异常: {str(e)}",
                    elapsed=time.time() - start,
                )
                logger.error(f"工具执行异常: {tool_name}", exc_info=True)

        # 不管成功失败都记录 trace
        trace_entry = {
            "tool": tool_name,
            "arguments": arguments,
            "ok": result.ok,
            "output_preview": result.output[:200] if result.output else "",
            "error": result.error,
            "elapsed": round(result.elapsed, 3),
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._trace.append(trace_entry)
        logger.info(f"工具执行: {tool_name} -> ok={result.ok}, "
                    f"elapsed={result.elapsed:.3f}s")

        return result

    def get_trace(self) -> list[dict]:
        """获取所有工具调用的 trace 记录"""
        return list(self._trace)

    def describe(self) -> str:
        """用于调试/日志：列出所有注册的工具"""
        lines = []
        for name, spec in self._specs.items():
            lines.append(f"  - {name}: {spec.description}")
        return "\n".join(lines)
