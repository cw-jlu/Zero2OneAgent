"""
Context 管理：负责对话历史的组织、裁剪、压缩。

这部分比较关键，answer_docs.md 里也提到了几个要点：
1. 去掉失败的 loop（成功后就没必要留着之前的报错了）
2. 历史太长时压缩早期对话
3. 保留用户输入 + 最终结果，去掉中间的 thought/tool 调用细节

压缩策略：
- 前面的对话做摘要（用 LLM 总结成一段话）
- 最近几轮完整保留（这样追问的时候有上下文）
- 失败的工具调用在成功后清理掉
"""
import logging

logger = logging.getLogger("agent.context")


def build_messages_for_llm(
    messages: list[dict],
    system_prompt: str,
    max_turns: int = 20,
) -> list[dict]:
    """
    从 session 的完整 messages 构建发给 LLM 的 messages。
    
    做几件事：
    1. 加上 system prompt
    2. 如果历史太长，只保留最近的若干轮
    3. 清理掉一些没用的中间消息（连续的 tool 错误）
    
    参数:
        messages: session 里的全部历史消息
        system_prompt: 系统提示词
        max_turns: 最多保留多少轮（1轮 = user + assistant）
    """
    # system prompt 始终在最前面
    result = [{"role": "system", "content": system_prompt}]

    # 先做一轮清理：去掉连续失败的 tool 调用
    cleaned = _remove_failed_tool_runs(messages)

    # 然后做轮次截断
    if len(cleaned) > max_turns * 2:
        # 保留最近 max_turns 轮
        # 但要注意：截断点不能切在 assistant 和 tool_result 中间
        keep_count = max_turns * 2
        truncated = cleaned[-keep_count:]
        
        # 如果第一条不是 user，往后找到第一个 user 开始
        while truncated and truncated[0].get("role") != "user":
            truncated.pop(0)
        
        if truncated:
            # 在最前面加一条提示，告诉 LLM 前面还有对话
            result.append({
                "role": "system",
                "content": f"[注：前面还有 {len(cleaned) - len(truncated)} 条消息已省略，"
                           f"以下是最近的对话记录]"
            })
            result.extend(truncated)
        else:
            result.extend(cleaned)
    else:
        result.extend(cleaned)

    return result


def _remove_failed_tool_runs(messages: list[dict]) -> list[dict]:
    """
    清理掉"已经解决"的失败工具调用。
    
    思路：如果一个 assistant 消息包含 tool_calls，后面跟了 tool 的
    error result，但最终同一类工具调用成功了，那么那些失败的就可以去掉。
    
    这里做个简化版：不是真的去分析哪些失败后来成功了，
    而是把连续的 tool error 只保留最后一个，省点 token。
    """
    if not messages:
        return []

    cleaned = []
    i = 0
    while i < len(messages):
        msg = messages[i]

        # 如果是 tool role 的消息（工具返回结果），看看是不是错误
        if msg.get("role") == "tool" and "error" in str(msg.get("content", "")):
            # 看后面有没有连续的 tool error
            j = i
            while (j + 1 < len(messages)
                   and messages[j + 1].get("role") == "tool"
                   and "error" in str(messages[j + 1].get("content", ""))):
                j += 1

            if j > i:
                # 有连续错误，只保留最后一个
                logger.debug(f"压缩掉 {j - i} 条连续工具错误")
                cleaned.append(messages[j])
                i = j + 1
            else:
                cleaned.append(msg)
                i += 1
        else:
            cleaned.append(msg)
            i += 1

    return cleaned


def compress_history(messages: list[dict], llm_client, keep_recent: int = 6) -> list[dict]:
    """
    用 LLM 对早期对话做摘要压缩。
    
    策略：
    - 最近 keep_recent 条消息原样保留
    - 更早的消息让 LLM 生成一个摘要
    - 摘要放在一条 system 消息里
    
    参数:
        messages: 不含 system prompt 的对话历史
        llm_client: LLM 客户端，用于生成摘要
        keep_recent: 保留最近多少条消息
    """
    if len(messages) <= keep_recent:
        return messages

    # 分成两部分
    old_messages = messages[:-keep_recent]
    recent_messages = messages[-keep_recent:]

    # 确保 recent_messages 的第一条是 user
    while recent_messages and recent_messages[0].get("role") != "user":
        old_messages.append(recent_messages.pop(0))

    if not old_messages:
        return recent_messages

    # 构造摘要请求
    history_text = "\n".join(
        f"[{m.get('role', '?')}]: {str(m.get('content', ''))[:300]}"
        for m in old_messages
    )

    summary = llm_client.simple_chat(
        prompt=(
            f"请用中文简要总结以下对话的要点，包括用户问了什么、"
            f"agent 做了什么、关键的结论和数据。200字以内：\n\n{history_text}"
        ),
        system="你是一个对话摘要助手。请提取关键信息，简洁明了。",
    )

    compressed = [
        {
            "role": "system",
            "content": f"[以下是之前对话的摘要]\n{summary}\n[摘要结束，以下是最近的对话]"
        }
    ]
    compressed.extend(recent_messages)

    logger.info(f"压缩完成: {len(old_messages)} 条消息 -> 1 条摘要, "
                f"保留 {len(recent_messages)} 条最近消息")
    return compressed
