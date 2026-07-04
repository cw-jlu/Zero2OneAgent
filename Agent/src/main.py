"""
CLI 入口。终端交互界面。

支持的命令：
  /new          创建新 session
  /switch <id>  切换到指定 session
  /list         列出所有 session
  /trace        查看当前 session 的工具调用记录
  /debug        切换 debug 模式
  /help         显示帮助
  /quit         退出

普通输入直接发给 Agent 处理。
"""
import sys
import json
import argparse

from config import load_config
from logger import setup_logging
from llm import LLMClient
from tool_registry import ToolRegistry, ToolSpec
from tools import calculator, search, weather, todo
from session import SessionManager
from loop import AgentLoop


def _register_tools(registry: ToolRegistry, session_id: str) -> None:
    """注册所有工具到 registry"""
    # calculator
    registry.register(calculator.SPEC, calculator.handler)
    # search
    registry.register(search.SPEC, search.handler)
    # weather
    registry.register(weather.SPEC, weather.handler)
    # todo —— 需要绑定 session_id
    registry.register(todo.SPEC, todo.create_handler(session_id))


def _print_banner():
    print("\n" + "=" * 50)
    print("  🤖 Mini Agent - 从零实现的最小可用 Agent")
    print("=" * 50)
    print("  输入问题开始对话，输入 /help 查看命令")
    print()


def _print_help():
    print("""
可用命令：
  /new            创建新的对话 session
  /switch <id>    切换到指定 session
  /list           列出所有 session
  /trace          查看工具调用日志
  /debug          切换调试模式
  /help           显示此帮助
  /quit           退出程序
""")


def main():
    parser = argparse.ArgumentParser(description="Mini Agent CLI")
    parser.add_argument("--session", "-s", default="", help="指定 session ID")
    parser.add_argument("--debug", "-d", action="store_true", help="开启调试模式")
    args = parser.parse_args()

    # 加载配置
    config = load_config()
    if not config.api_key:
        print("❌ 未设置 LLM_API_KEY，请在 .env 文件中配置")
        print(f"   参考: {config.session_dir}/../.env.example")
        sys.exit(1)

    # 初始化日志
    setup_logging(config.log_dir, debug=args.debug)

    # 初始化组件
    llm = LLMClient(config)
    session_mgr = SessionManager(config)

    # 创建或恢复 session
    if args.session:
        session = session_mgr.get_or_create(args.session)
        print(f"📎 使用 session: {session.session_id}")
    else:
        session = session_mgr.create()
        print(f"📎 新建 session: {session.session_id}")

    # 注册工具 & 创建 loop
    registry = ToolRegistry()
    _register_tools(registry, session.session_id)
    agent = AgentLoop(llm, registry, config)

    _print_banner()

    if session.messages:
        print(f"💬 恢复了 {len(session.messages)} 条历史消息\n")

    # 交互循环
    debug_mode = args.debug
    while True:
        try:
            user_input = input("You > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 再见！")
            break

        if not user_input:
            continue

        # 处理命令
        if user_input.startswith("/"):
            cmd_parts = user_input.split(maxsplit=1)
            cmd = cmd_parts[0].lower()

            if cmd == "/quit":
                session_mgr.save(session.session_id)
                print("👋 再见！")
                break

            elif cmd == "/help":
                _print_help()

            elif cmd == "/new":
                session_mgr.save(session.session_id)
                session = session_mgr.create()
                # 重新注册工具（绑定新 session_id）
                registry = ToolRegistry()
                _register_tools(registry, session.session_id)
                agent = AgentLoop(llm, registry, config)
                print(f"📎 新建 session: {session.session_id}")

            elif cmd == "/switch":
                if len(cmd_parts) < 2:
                    print("用法: /switch <session_id>")
                else:
                    target_id = cmd_parts[1].strip()
                    session_mgr.save(session.session_id)
                    session = session_mgr.get_or_create(target_id)
                    registry = ToolRegistry()
                    _register_tools(registry, session.session_id)
                    agent = AgentLoop(llm, registry, config)
                    print(f"📎 切换到 session: {session.session_id} "
                          f"(历史消息: {len(session.messages)})")

            elif cmd == "/list":
                sessions = session_mgr.list_sessions()
                if not sessions:
                    print("暂无 session")
                else:
                    print(f"{'ID':<12} {'消息数':<8} {'最后活跃':<20}")
                    print("-" * 40)
                    for s in sessions:
                        marker = " ←" if s["session_id"] == session.session_id else ""
                        print(f"{s['session_id']:<12} {s['message_count']:<8} "
                              f"{s['last_active']:<20}{marker}")

            elif cmd == "/trace":
                trace = registry.get_trace()
                if not trace:
                    print("暂无工具调用记录")
                else:
                    print(f"\n工具调用记录 (共 {len(trace)} 条)：")
                    for i, t in enumerate(trace, 1):
                        status = "✅" if t["ok"] else "❌"
                        print(f"  {i}. {status} {t['tool']} "
                              f"({t['elapsed']}s) @ {t['timestamp']}")
                        if t["error"]:
                            print(f"     错误: {t['error']}")
                    print()

            elif cmd == "/debug":
                debug_mode = not debug_mode
                print(f"调试模式: {'开启' if debug_mode else '关闭'}")

            else:
                print(f"未知命令: {cmd}，输入 /help 查看帮助")

            continue

        # 普通输入：发给 Agent
        print("🤔 思考中...")
        try:
            response = agent.run(session, user_input)
            print(f"\nAgent > {response}\n")
        except Exception as e:
            print(f"\n❌ 出错了: {e}\n")
            if debug_mode:
                import traceback
                traceback.print_exc()

        # 每次对话后保存 session
        session_mgr.save(session.session_id)


if __name__ == "__main__":
    main()
