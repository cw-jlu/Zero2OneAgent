"""
待办事项（TODO）工具。
每个 session 有自己独立的 todo list，存在内存里。
这是个有状态的工具，所以要在 session 层面管理数据。
"""
from tool_registry import ToolSpec, ToolResult


SPEC = ToolSpec(
    name="todo",
    description="管理待办事项列表。支持添加(add)、查看(list)、完成(done)、删除(delete)操作。",
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["add", "list", "done", "delete"],
                "description": "操作类型"
            },
            "content": {
                "type": "string",
                "description": "待办内容（add 时必填）"
            },
            "index": {
                "type": "integer",
                "description": "待办序号（done/delete 时使用，从1开始）"
            }
        },
        "required": ["action"]
    }
)


class TodoStore:
    """
    简单的 todo 存储，按 session_id 隔离。
    之所以不用数据库，是因为这就是个 demo，
    复杂的持久化方案在这里 overkill。
    """
    def __init__(self):
        # {session_id: [{"text": ..., "done": False}, ...]}
        self._data: dict[str, list[dict]] = {}

    def _get_list(self, session_id: str) -> list[dict]:
        if session_id not in self._data:
            self._data[session_id] = []
        return self._data[session_id]

    def add(self, session_id: str, text: str) -> str:
        items = self._get_list(session_id)
        items.append({"text": text, "done": False})
        return f"✅ 已添加待办: {text}（共 {len(items)} 项）"

    def list_all(self, session_id: str) -> str:
        items = self._get_list(session_id)
        if not items:
            return "📋 待办列表为空"

        lines = ["📋 待办列表："]
        for i, item in enumerate(items, 1):
            status = "✅" if item["done"] else "⬜"
            lines.append(f"  {i}. {status} {item['text']}")
        return "\n".join(lines)

    def done(self, session_id: str, index: int) -> str:
        items = self._get_list(session_id)
        if index < 1 or index > len(items):
            return f"❌ 序号 {index} 不存在，当前共 {len(items)} 项"
        items[index - 1]["done"] = True
        return f"✅ 已完成: {items[index - 1]['text']}"

    def delete(self, session_id: str, index: int) -> str:
        items = self._get_list(session_id)
        if index < 1 or index > len(items):
            return f"❌ 序号 {index} 不存在，当前共 {len(items)} 项"
        removed = items.pop(index - 1)
        return f"🗑️ 已删除: {removed['text']}"


# 全局实例，所有 session 共享（通过 session_id 隔离数据）
_store = TodoStore()


def create_handler(session_id: str):
    """
    为指定 session 创建一个 handler。
    因为 todo 是有状态的，需要知道当前 session，
    所以用闭包包一下 session_id。
    """
    def handler(args: dict) -> ToolResult:
        action = args.get("action", "").strip()
        content = args.get("content", "").strip()
        index = args.get("index", 0)
        # index 可能是字符串，兼容一下
        if isinstance(index, str):
            try:
                index = int(index)
            except ValueError:
                index = 0

        try:
            if action == "add":
                if not content:
                    return ToolResult(ok=False, output="", error="添加待办需要提供 content")
                msg = _store.add(session_id, content)
            elif action == "list":
                msg = _store.list_all(session_id)
            elif action == "done":
                msg = _store.done(session_id, index)
            elif action == "delete":
                msg = _store.delete(session_id, index)
            else:
                return ToolResult(ok=False, output="",
                                error=f"不支持的操作: {action}，可用: add/list/done/delete")
            return ToolResult(ok=True, output=msg)
        except Exception as e:
            return ToolResult(ok=False, output="", error=f"操作失败: {e}")

    return handler
