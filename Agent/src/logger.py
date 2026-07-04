"""
日志配置。
单独拎出来是因为日志格式和输出目标需要统一管理。
"""
import os
import logging
from pathlib import Path


def setup_logging(log_dir: str, debug: bool = False):
    """
    配置日志：同时输出到文件和控制台。
    
    文件日志记详细的，控制台只显示 WARNING 以上（除非开 debug）。
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    log_file = log_path / "agent.log"

    # root logger
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # 文件 handler：记所有级别
    fh = logging.FileHandler(str(log_file), encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    root.addHandler(fh)

    # 控制台 handler：默认 WARNING，debug 模式下 DEBUG
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG if debug else logging.WARNING)
    ch.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s: %(message)s",
        datefmt="%H:%M:%S"
    ))
    root.addHandler(ch)

    # openai 库的日志太吵了，压一下
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
