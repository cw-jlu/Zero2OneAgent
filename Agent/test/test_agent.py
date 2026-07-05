"""
测试用例。

测试策略：
1. 工具测试：每个工具单独测试，确保 handler 正确
2. 注册机制测试：测试 ToolRegistry 的注册、查找、执行
3. Session 测试：测试创建、切换、持久化
4. Context 测试：测试历史压缩和清理
5. 集成测试：端到端测试 agent loop（需要真实 LLM API）

前面 1-4 是纯单元测试，不需要 API key。
第 5 项需要配置好 .env 才能跑。
"""
import sys
import os
import json
import time
import tempfile
from pathlib import Path

# 把 src 加到 path 里
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from config import AgentConfig, load_config
from tool_registry import ToolRegistry, ToolSpec, ToolResult
from tools.calculator import SPEC as CALC_SPEC, handler as calc_handler
from tools.search import SPEC as SEARCH_SPEC, handler as search_handler
from tools.weather import SPEC as WEATHER_SPEC, handler as weather_handler
from tools.todo import SPEC as TODO_SPEC, create_handler as create_todo_handler
from session import Session, SessionManager
from context import build_messages_for_llm, _remove_failed_tool_runs


# ---------- 工具测试 ----------

def test_calculator():
    """测试计算器工具"""
    print("=== 测试: calculator ===")

    # 基本运算
    r = calc_handler({"expression": "2 + 3"})
    assert r.ok and r.output == "5", f"2+3 应该等于 5，得到 {r.output}"

    # 复杂表达式
    r = calc_handler({"expression": "sqrt(144) + pow(2, 10)"})
    assert r.ok and r.output == "1036.0", f"期望 1036.0，得到 {r.output}"

    # 除法
    r = calc_handler({"expression": "10 / 3"})
    assert r.ok, f"除法应该成功: {r.error}"

    # 空表达式
    r = calc_handler({"expression": ""})
    assert not r.ok, "空表达式应该失败"

    # 语法错误
    r = calc_handler({"expression": "2 +* 3"})
    assert not r.ok, "语法错误应该失败"

    # 安全性：不能调用危险函数
    r = calc_handler({"expression": "__import__('os').system('ls')"})
    assert not r.ok, "不安全的表达式应该被拦截"

    print("  ✅ 全部通过\n")


def test_search():
    """测试搜索工具"""
    print("=== 测试: search ===")

    # 能匹配到的关键词
    r = search_handler({"query": "python"})
    assert r.ok, f"搜索应该成功: {r.error}"
    assert "Python" in r.output, "结果里应该有 Python"

    # 匹配不到的关键词也应该返回结果（兜底）
    r = search_handler({"query": "量子力学"})
    assert r.ok, "未匹配的搜索也应该返回结果"
    assert "量子力学" in r.output, "结果里应该包含搜索词"

    # 空查询
    r = search_handler({"query": ""})
    assert not r.ok, "空查询应该失败"

    print("  ✅ 全部通过\n")


def test_weather():
    """测试天气工具"""
    print("=== 测试: weather ===")

    # 已有城市
    r = weather_handler({"city": "Beijing"})
    assert r.ok, f"查询北京天气应该成功: {r.error}"
    assert "Beijing" in r.output, "结果中应包含城市名称"

    # 英文城市
    r = weather_handler({"city": "Tokyo"})
    assert r.ok, "Tokyo 查询应该成功"

    # 空城市
    r = weather_handler({"city": ""})
    assert not r.ok, "空城市应该失败"

    print("  ✅ 全部通过\n")


def test_todo():
    """测试待办工具（有状态工具）"""
    print("=== 测试: todo ===")

    handler = create_todo_handler("test_session_1")

    # 一开始是空的
    r = handler({"action": "list"})
    assert r.ok and "为空" in r.output

    # 添加
    r = handler({"action": "add", "content": "写测试用例"})
    assert r.ok and "已添加" in r.output

    r = handler({"action": "add", "content": "写 README"})
    assert r.ok

    # 列表
    r = handler({"action": "list"})
    assert r.ok and "写测试用例" in r.output and "写 README" in r.output

    # 完成
    r = handler({"action": "done", "index": 1})
    assert r.ok and "已完成" in r.output

    # 再次列出，第一个应该是完成状态
    r = handler({"action": "list"})
    assert "✅" in r.output

    # 删除
    r = handler({"action": "delete", "index": 2})
    assert r.ok and "已删除" in r.output

    # 不同 session 应该隔离
    handler2 = create_todo_handler("test_session_2")
    r2 = handler2({"action": "list"})
    assert "为空" in r2.output, "不同 session 的 todo 应该隔离"

    # 无效操作
    r = handler({"action": "fly"})
    assert not r.ok

    print("  ✅ 全部通过\n")


# ---------- 注册机制测试 ----------

def test_tool_registry():
    """测试工具注册表"""
    print("=== 测试: ToolRegistry ===")

    registry = ToolRegistry()
    
    # 注册工具
    registry.register(CALC_SPEC, calc_handler)
    registry.register(SEARCH_SPEC, search_handler)
    
    # 获取 LLM 格式的工具列表
    tools_for_llm = registry.get_tools_for_llm()
    assert len(tools_for_llm) == 2
    names = [t["function"]["name"] for t in tools_for_llm]
    assert "calculator" in names
    assert "search" in names

    # 执行已注册的工具
    result = registry.execute("calculator", {"expression": "1 + 1"})
    assert result.ok and result.output == "2"

    # 执行未注册的工具
    result = registry.execute("fly_to_moon", {})
    assert not result.ok and "未知工具" in result.error

    # trace 应该有记录
    trace = registry.get_trace()
    assert len(trace) == 2
    assert trace[0]["tool"] == "calculator"
    assert trace[0]["ok"] is True
    assert trace[1]["tool"] == "fly_to_moon"
    assert trace[1]["ok"] is False

    print("  ✅ 全部通过\n")


def test_tool_schema_format():
    """测试工具 schema 是否符合 OpenAI function calling 格式"""
    print("=== 测试: Tool Schema 格式 ===")

    specs = [CALC_SPEC, SEARCH_SPEC, WEATHER_SPEC, TODO_SPEC]
    for spec in specs:
        assert spec.name, f"工具必须有 name"
        assert spec.description, f"{spec.name} 必须有 description"
        assert isinstance(spec.parameters, dict), f"{spec.name} 的 parameters 必须是 dict"
        assert spec.parameters.get("type") == "object", \
            f"{spec.name} 的 parameters.type 必须是 object"
        assert "properties" in spec.parameters, \
            f"{spec.name} 的 parameters 必须包含 properties"

    print("  ✅ 全部通过\n")


# ---------- Session 测试 ----------

def test_session_basic():
    """测试 session 的基本操作"""
    print("=== 测试: Session 基本操作 ===")

    # 用临时目录
    with tempfile.TemporaryDirectory() as tmpdir:
        config = AgentConfig(
            api_key="", base_url="", model="",
            max_loop_steps=10, max_turns=20, compress_threshold=16,
            session_dir=tmpdir, log_dir=tmpdir,
        )
        mgr = SessionManager(config)

        # 创建
        s1 = mgr.create("s1")
        assert s1.session_id == "s1"
        assert s1.messages == []

        # 添加消息
        s1.messages.append({"role": "user", "content": "hello"})
        mgr.save("s1")

        # 重新加载
        mgr2 = SessionManager(config)
        s1_loaded = mgr2.get("s1")
        assert s1_loaded is not None
        assert len(s1_loaded.messages) == 1
        assert s1_loaded.messages[0]["content"] == "hello"

        # 列出
        sessions = mgr2.list_sessions()
        assert len(sessions) == 1

        # 删除
        assert mgr2.delete("s1")
        assert mgr2.get("s1") is None

    print("  ✅ 全部通过\n")


def test_session_isolation():
    """测试 session 隔离"""
    print("=== 测试: Session 隔离 ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        config = AgentConfig(
            api_key="", base_url="", model="",
            max_loop_steps=10, max_turns=20, compress_threshold=16,
            session_dir=tmpdir, log_dir=tmpdir,
        )
        mgr = SessionManager(config)

        s1 = mgr.create("window1")
        s2 = mgr.create("window2")

        s1.messages.append({"role": "user", "content": "查天气"})
        s2.messages.append({"role": "user", "content": "写周报"})

        # 两个 session 的消息不应该互相影响
        assert len(s1.messages) == 1
        assert len(s2.messages) == 1
        assert s1.messages[0]["content"] == "查天气"
        assert s2.messages[0]["content"] == "写周报"

    print("  ✅ 全部通过\n")


# ---------- Context 测试 ----------

def test_context_build():
    """测试 context 构建"""
    print("=== 测试: Context 构建 ===")

    messages = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！"},
        {"role": "user", "content": "今天天气怎么样"},
        {"role": "assistant", "content": "让我查一下"},
    ]

    result = build_messages_for_llm(messages, "你是助手", max_turns=10)
    
    # 第一条应该是 system prompt
    assert result[0]["role"] == "system"
    assert result[0]["content"] == "你是助手"
    # 后面是历史消息
    assert len(result) == 5  # system + 4条消息

    print("  ✅ 全部通过\n")


def test_context_truncation():
    """测试 context 截断"""
    print("=== 测试: Context 截断 ===")

    # 生成很多消息
    messages = []
    for i in range(30):
        messages.append({"role": "user", "content": f"问题 {i}"})
        messages.append({"role": "assistant", "content": f"回答 {i}"})

    # max_turns=5 → 最多保留 10 条消息
    result = build_messages_for_llm(messages, "你是助手", max_turns=5)

    # 应该有截断提示
    has_truncation_hint = any(
        "省略" in msg.get("content", "") 
        for msg in result 
        if msg["role"] == "system"
    )
    assert has_truncation_hint, "应该有截断提示"

    # 不应该超过 max_turns * 2 + 2（system + truncation hint）
    assert len(result) <= 5 * 2 + 2

    print("  ✅ 全部通过\n")


def test_remove_failed_tool_runs():
    """测试清理失败工具调用"""
    print("=== 测试: 清理失败工具调用 ===")

    messages = [
        {"role": "user", "content": "算一下"},
        {"role": "tool", "content": "error: 计算失败"},
        {"role": "tool", "content": "error: 还是失败"},
        {"role": "tool", "content": "error: 第三次失败"},
        {"role": "tool", "content": "结果是 42"},
    ]

    cleaned = _remove_failed_tool_runs(messages)
    # 连续 3 个错误应该被压缩成最后一个
    assert len(cleaned) == 3  # user + 最后一个错误 + 成功结果

    print("  ✅ 全部通过\n")


# ---------- 集成测试（需要 API key） ----------

def test_agent_loop_integration():
    """
    端到端集成测试。
    需要配置好 .env 中的 LLM_API_KEY 才能跑。
    """
    print("=== 测试: Agent Loop 集成（需要 API） ===")

    config = load_config()
    if not config.api_key:
        print("  ⏭ 跳过（未配置 LLM_API_KEY）\n")
        return

    from llm import LLMClient
    from loop import AgentLoop

    with tempfile.TemporaryDirectory() as tmpdir:
        config.session_dir = tmpdir
        config.log_dir = tmpdir

        llm = LLMClient(config)
        registry = ToolRegistry()
        registry.register(CALC_SPEC, calc_handler)
        registry.register(SEARCH_SPEC, search_handler)
        registry.register(WEATHER_SPEC, weather_handler)
        registry.register(TODO_SPEC, create_todo_handler("test_integration"))

        agent = AgentLoop(llm, registry, config)
        session = Session(session_id="test_integration")

        # 测试1: 纯对话（不需要工具）
        print("  测试 1: 纯对话...")
        resp = agent.run(session, "你好，请用一句话介绍你自己")
        assert resp, "应该有回复"
        assert len(resp) > 5, "回复不应该太短"
        print(f"    回复: {resp[:80]}...")

        # 测试2: 工具调用（计算器）
        print("  测试 2: 工具调用 - 计算器...")
        resp = agent.run(session, "请帮我算一下 123 * 456 + 789")
        assert resp, "应该有回复"
        # 结果应该包含 56877
        print(f"    回复: {resp[:80]}...")

        # 测试3: 工具调用（天气）
        print("  测试 3: 工具调用 - 天气...")
        resp = agent.run(session, "北京今天天气怎么样？")
        assert resp, "应该有回复"
        print(f"    回复: {resp[:80]}...")

        # 测试4: 追问（基于之前的上下文）
        print("  测试 4: 追问...")
        resp = agent.run(session, "上海呢？")
        assert resp, "追问应该有回复"
        print(f"    回复: {resp[:80]}...")

        # 测试5: 工具调用（todo）
        print("  测试 5: 工具调用 - 待办...")
        resp = agent.run(session, "帮我添加一个待办：完成 Agent 作业")
        assert resp, "应该有回复"
        print(f"    回复: {resp[:80]}...")

        # 测试6: 追问带工具
        print("  测试 6: 追问带工具...")
        resp = agent.run(session, "再帮我看看我的待办列表")
        assert resp, "应该有回复"
        print(f"    回复: {resp[:80]}...")

        # 验证 trace
        trace = registry.get_trace()
        assert len(trace) > 0, "应该有工具调用记录"
        print(f"  工具调用次数: {len(trace)}")

    print("  ✅ 全部通过\n")


def run_all_tests():
    print("\n🧪 开始运行测试...\n")
    start = time.time()

    # 单元测试（不需要 API）
    test_calculator()
    test_search()
    test_weather()
    test_todo()
    test_tool_registry()
    test_tool_schema_format()
    test_session_basic()
    test_session_isolation()
    test_context_build()
    test_context_truncation()
    test_remove_failed_tool_runs()

    # 集成测试（需要 API）
    test_agent_loop_integration()

    elapsed = time.time() - start
    print(f"🎉 所有测试完成! 耗时 {elapsed:.1f}s\n")


if __name__ == "__main__":
    run_all_tests()
