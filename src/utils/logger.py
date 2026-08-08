"""
Structured logging module for AI Agent tracking.
"""

import logging
import sys
from pathlib import Path


def get_logger(name: str = "redecide_agent") -> logging.Logger:
    """Return a configured logger writing to stderr and logs/agent.log."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s")

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    logs_dir = Path(__file__).resolve().parents[2] / "logs"
    if logs_dir.is_dir():
        file_handler = logging.FileHandler(logs_dir / "agent.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
