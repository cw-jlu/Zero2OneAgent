#全局配置。从 .env 或环境变量中读取，统一管理。
import os
from pathlib import Path
from dataclasses import dataclass

# 先尝试加载 .env，没有 dotenv 也不报错
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass


@dataclass
class AgentConfig:
    api_key: str
    base_url: str
    model: str
    max_loop_steps: int
    max_turns: int
    compress_threshold: int
    session_dir: str
    log_dir: str


def load_config() -> AgentConfig:
    """所有配置统一从环境变量读，默认值只在这一个地方维护"""
    base = Path(__file__).parent
    return AgentConfig(
        api_key=os.getenv("LLM_API_KEY", ""),
        base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
        model=os.getenv("LLM_MODEL", "deepseek-chat"),
        max_loop_steps=int(os.getenv("MAX_LOOP_STEPS", "10")),
        max_turns=int(os.getenv("MAX_TURNS", "20")),
        compress_threshold=int(os.getenv("COMPRESS_THRESHOLD", "16")),
        session_dir=os.getenv("SESSION_DIR", str(base / "sessions")),
        log_dir=os.getenv("LOG_DIR", str(base / "logs")),
    )
