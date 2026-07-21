from __future__ import annotations

"""Logging setup for the league-predict engine."""

import logging


def setup_logger(name: str = "predict") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    # 清理旧 handler 防止 pytest 并行时累积
    logger.handlers.clear()
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter("[%(name)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


logger = setup_logger("predict")


__all__ = ["setup_logger", "logger"]
