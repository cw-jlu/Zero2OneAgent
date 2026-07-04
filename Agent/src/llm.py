#LLM调用封装
import json
import time
import logging
from openai import OpenAI

from config import AgentConfig

logger = logging.getLogger("agent.llm")


class LLMClient:
    def __init__(self, config: AgentConfig):
        self.client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
        )
        self.model = config.model
        self._call_count = 0

    def chat(self, messages: list[dict], tools: list[dict] | None = None,
             temperature: float = 0.7) -> dict:
        """
        发起一次 chat completion 请求。
        返回 assistant 的完整 message dict（包含 content 和可能的 tool_calls）。
        
        这里有意不做重试——上层 loop 自己处理异常就好，
        重试逻辑裹在底层反而容易掩盖问题。
        """
        self._call_count += 1
        call_id = self._call_count

        logger.debug(f"[LLM call #{call_id}] model={self.model}, "
                     f"messages={len(messages)}, tools={len(tools) if tools else 0}")

        start = time.time()
        
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            # 让模型自己决定要不要调工具，不强制
            kwargs["tool_choice"] = "auto"

        response = self.client.chat.completions.create(**kwargs)
        elapsed = time.time() - start

        msg = response.choices[0].message
        logger.debug(f"[LLM call #{call_id}] done in {elapsed:.2f}s, "
                     f"finish_reason={response.choices[0].finish_reason}")

        # 转成普通 dict，方便后面序列化
        result = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            result["tool_calls"] = []
            for tc in msg.tool_calls:
                result["tool_calls"].append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                })
        return result

    def simple_chat(self, prompt: str, system: str = "") -> str:
        """
        简单的单轮对话，用于压缩摘要之类的辅助任务。
        不带工具，不复杂。
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        
        result = self.chat(messages, temperature=0.3)
        return result.get("content", "")
