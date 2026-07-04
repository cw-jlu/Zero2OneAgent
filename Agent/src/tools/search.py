"""
搜索工具（mock 版本）。
真实场景可以接 Google/Bing API，这里先用预置数据模拟。
返回格式尽量接近真实搜索结果，方便后面替换。
"""
from tool_registry import ToolSpec, ToolResult


SPEC = ToolSpec(
    name="search",
    description="搜索互联网信息。输入查询关键词，返回相关结果摘要。（当前为模拟数据）",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词"
            }
        },
        "required": ["query"]
    }
)

# mock 数据，按关键词匹配
_MOCK_DATA = {
    "python": [
        {"title": "Python 官方文档", "snippet": "Python 是一种解释型、面向对象的高级编程语言。最新版本为 3.12。"},
        {"title": "Python 教程 - 菜鸟教程", "snippet": "Python 语法简洁清晰，适合初学者入门。"},
    ],
    "机器学习": [
        {"title": "什么是机器学习", "snippet": "机器学习是人工智能的一个分支，通过数据训练模型来做预测。"},
        {"title": "sklearn 入门指南", "snippet": "scikit-learn 提供了常用的分类、回归、聚类算法实现。"},
    ],
    "agent": [
        {"title": "LLM Agent 架构综述", "snippet": "典型的 Agent 由 LLM + 工具 + 记忆三部分组成，通过 ReAct 循环执行任务。"},
        {"title": "Claude Code 源码分析", "snippet": "Claude Code 使用 Tool 注册机制，LLM 通过 function calling 选择工具。"},
    ],
}


def handler(args: dict) -> ToolResult:
    query = args.get("query", "").strip()
    if not query:
        return ToolResult(ok=False, output="", error="搜索关键词不能为空")

    # 简单关键词匹配
    results = []
    query_lower = query.lower()
    for keyword, items in _MOCK_DATA.items():
        if keyword in query_lower or query_lower in keyword:
            results.extend(items)

    if not results:
        # 兜底：返回一个通用结果，避免 LLM 拿到空结果
        results = [
            {"title": f"关于「{query}」的搜索结果",
             "snippet": f"找到了一些关于 {query} 的信息，但具体内容需要进一步确认。"
             + " 建议您提供更具体的关键词重新搜索。"}
        ]

    # 格式化输出
    lines = [f"搜索「{query}」的结果：\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}")
        lines.append(f"   {r['snippet']}\n")

    return ToolResult(ok=True, output="\n".join(lines))
