from __future__ import annotations

"""Logging setup for the league-predict engine."""

import logging
import os


def setup_logger(name: str = "predict") -> logging.Logger:
    logger = logging.getLogger(name)
    # 支持环境变量 LEAGUE_PREDICT_LOG_LEVEL 配置日志级别
    level_str = os.environ.get("LEAGUE_PREDICT_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_str, logging.INFO)
    logger.setLevel(level)
    # 清理旧 handler 防止 pytest 并行时累积
    logger.handlers.clear()
    handler = logging.StreamHandler()
    handler.setLevel(level)
    formatter = logging.Formatter("[%(name)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


logger = setup_logger("predict")


__all__ = ["setup_logger", "logger"]
