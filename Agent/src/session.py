"""
Session 管理。

每个 session 代表一个独立的对话窗口，有自己的：
- 对话历史 (messages)
- context 状态
- 工具 trace

不同 session 之间完全隔离，参考题目要求：
  用户A窗口1查天气 和 窗口2写周报，互不影响。

持久化方面，session 数据存到磁盘上的 JSON 文件，
启动时按 session_id 加载，退出时自动保存。
"""
import json
import uuid
import time
import os
import logging
from pathlib import Path
from dataclasses import dataclass, field

from config import AgentConfig

logger = logging.getLogger("agent.session")


@dataclass
class Session:
    session_id: str
    # 完整的对话历史，格式跟 OpenAI messages 一样
    messages: list[dict] = field(default_factory=list)
    # 创建时间
    created_at: str = ""
    # 上次活跃时间
    last_active: str = ""
    # 元信息，比如用户自定义的标签之类的
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "messages": self.messages,
            "created_at": self.created_at,
            "last_active": self.last_active,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        return cls(
            session_id=data["session_id"],
            messages=data.get("messages", []),
            created_at=data.get("created_at", ""),
            last_active=data.get("last_active", ""),
            metadata=data.get("metadata", {}),
        )


class SessionManager:
    """
    管理多个 session 的生命周期。
    
    设计上比较简单粗暴：
    - 内存里维护一个 {session_id: Session} 的 dict
    - 需要持久化时整个 session 序列化成 JSON 写磁盘
    - 加载时反序列化回来
    
    没用 SQLite 之类的，因为对于这个 demo 来说 JSON 文件够用了，
    而且方便人工查看/调试。
    """
    def __init__(self, config: AgentConfig):
        self._sessions: dict[str, Session] = {}
        self._save_dir = Path(config.session_dir)
        self._save_dir.mkdir(parents=True, exist_ok=True)
        # 启动时加载已有 session
        self._load_all()

    def _load_all(self):
        """启动时从磁盘加载所有 session"""
        for f in self._save_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                session = Session.from_dict(data)
                self._sessions[session.session_id] = session
                logger.debug(f"加载 session: {session.session_id}")
            except Exception as e:
                logger.warning(f"加载 session 文件失败 {f}: {e}")

    def create(self, session_id: str = "") -> Session:
        """创建新 session"""
        if not session_id:
            session_id = str(uuid.uuid4())[:8]
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        session = Session(
            session_id=session_id,
            created_at=now,
            last_active=now,
        )
        self._sessions[session_id] = session
        self.save(session_id)
        logger.info(f"创建 session: {session_id}")
        return session

    def get(self, session_id: str) -> Session | None:
        """获取已有 session"""
        return self._sessions.get(session_id)

    def get_or_create(self, session_id: str) -> Session:
        """获取 session，不存在则创建"""
        session = self.get(session_id)
        if session is None:
            session = self.create(session_id)
        return session

    def save(self, session_id: str) -> None:
        """保存 session 到磁盘"""
        session = self._sessions.get(session_id)
        if session is None:
            return
        session.last_active = time.strftime("%Y-%m-%d %H:%M:%S")
        filepath = self._save_dir / f"{session_id}.json"
        filepath.write_text(
            json.dumps(session.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_sessions(self) -> list[dict]:
        """列出所有 session 的摘要信息"""
        result = []
        for sid, session in self._sessions.items():
            result.append({
                "session_id": sid,
                "created_at": session.created_at,
                "last_active": session.last_active,
                "message_count": len(session.messages),
            })
        return result

    def delete(self, session_id: str) -> bool:
        """删除 session"""
        if session_id in self._sessions:
            del self._sessions[session_id]
            filepath = self._save_dir / f"{session_id}.json"
            if filepath.exists():
                filepath.unlink()
            logger.info(f"删除 session: {session_id}")
            return True
        return False
