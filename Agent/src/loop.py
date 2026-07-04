"""
Agent 主循环。这是整个系统的核心。

参照题目要求的 loop 步骤：
  1. 接收用户输入
  2. 判断是直接回复，还是调用工具
  3. 调用工具
  4. 根据工具结果判断是继续 loop，还是返回结果给用户

实现思路：
- 把用户输入加到 session 的 messages 里
- 构建发给 LLM 的 context（system prompt + 历史 + 工具 schema）
- LLM 返回后检查有没有 tool_calls
  - 有：执行工具，把结果塞回 context，继续循环
  - 没有：直接返回 LLM 的回复
- 循环有上限，防止死循环

参考了 kdd 的 react.py 的循环结构，但这里用的是 OpenAI function calling
而不是让 LLM 输出 JSON 然后自己解析，这样更稳定。
Claude Code 的 query.ts 那个 while(true) 循环也是类似的思路。
"""
import json
import time
import logging
from pathlib import Path

from config import AgentConfig
from llm import LLMClient
from tool_registry import ToolRegistry
from session import Session
from context import build_messages_for_llm, compress_history

logger = logging.getLogger("agent.loop")


# 加载 system prompt
def _load_system_prompt() -> str:
    rules_file = Path(__file__).parent / "globalPrompts" / "rules.txt"
    if rules_file.exists():
        return rules_file.read_text(encoding="utf-8").strip()
    return "你是一个有用的助手。"


class AgentLoop:
    """
    Agent 的主循环逻辑。
    
    一个 AgentLoop 实例绑定一个 LLM 客户端和工具集，
    但可以服务多个 session（通过参数传入）。
    """
    def __init__(self, llm: LLMClient, tools: ToolRegistry, config: AgentConfig):
        self.llm = llm
        self.tools = tools
        self.config = config
        self.system_prompt = _load_system_prompt()

    def run(self, session: Session, user_input: str) -> str:
        """
        处理一次用户输入，返回 agent 的最终回复。
        
        这个方法会修改 session.messages（加入新的对话记录），
        调用者需要在合适的时机保存 session。
        """
        # 1. 把用户输入加到历史里
        session.messages.append({"role": "user", "content": user_input})

        # 2. 检查是否需要压缩历史
        if len(session.messages) > self.config.compress_threshold:
            logger.info("对话历史过长，触发压缩")
            # 只压缩非 system 消息
            session.messages = compress_history(
                session.messages, self.llm,
                keep_recent=8
            )

        # 3. 进入 agent loop
        final_response = ""
        step = 0

        while step < self.config.max_loop_steps:
            step += 1
            logger.info(f"--- Loop step {step}/{self.config.max_loop_steps} ---")

            # 构建发给 LLM 的完整 messages
            llm_messages = build_messages_for_llm(
                session.messages,
                self.system_prompt,
                max_turns=self.config.max_turns,
            )

            # 调 LLM
            try:
                llm_response = self.llm.chat(
                    messages=llm_messages,
                    tools=self.tools.get_tools_for_llm(),
                )
            except Exception as e:
                logger.error(f"LLM 调用失败: {e}", exc_info=True)
                final_response = f"抱歉，AI 服务调用出错了: {str(e)}"
                session.messages.append({"role": "assistant", "content": final_response})
                break

            # 4. 检查 LLM 的回复：有没有 tool_calls？
            tool_calls = llm_response.get("tool_calls")

            if not tool_calls:
                # 没有 tool_calls → 直接回复用户
                final_response = llm_response.get("content", "")
                session.messages.append({"role": "assistant", "content": final_response})
                logger.info("LLM 直接回复，退出 loop")
                break

            # 5. 有 tool_calls → 执行工具
            # 先把 assistant 的消息（含 tool_calls）加到历史里
            session.messages.append(llm_response)

            for tc in tool_calls:
                func_name = tc["function"]["name"]
                try:
                    func_args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    func_args = {}
                    logger.warning(f"工具参数解析失败: {tc['function']['arguments']}")

                logger.info(f"调用工具: {func_name}({json.dumps(func_args, ensure_ascii=False)})")

                # 执行工具
                result = self.tools.execute(func_name, func_args)

                # 构造 tool 的返回消息
                tool_content = result.output if result.ok else f"[工具错误] {result.error}"
                tool_msg = {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": tool_content,
                }
                session.messages.append(tool_msg)

            # 工具执行完了，继续循环让 LLM 根据工具结果决定下一步
            # （可能再调工具，也可能直接回复用户）
            logger.info("工具执行完毕，继续循环")

        else:
            # while 正常结束 = 达到了最大步数
            logger.warning(f"达到最大循环次数 {self.config.max_loop_steps}，强制退出")
            if not final_response:
                final_response = "抱歉，处理超时了。请简化你的问题重新试试。"
                session.messages.append({"role": "assistant", "content": final_response})

        return final_response