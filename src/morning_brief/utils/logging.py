"""Logging setup: console + rotating daily file in data/logs/."""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

_CONFIGURED = False


def get_logger(name: str = "morning_brief") -> logging.Logger:
    return logging.getLogger(name)


def setup_logging(log_dir: Path | str = "data/logs", level: str | None = None) -> logging.Logger:
    """Configure root logger once. Safe to call multiple times."""
    global _CONFIGURED
    logger = logging.getLogger("morning_brief")
    if _CONFIGURED:
        return logger

    level_name = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    logger.setLevel(getattr(logging, level_name, logging.INFO))
    logger.propagate = False

    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-7s  %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(fmt)
    logger.addHandler(console)

    try:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        from datetime import date

        file_handler = logging.FileHandler(log_path / f"brief-{date.today().isoformat()}.log")
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except OSError as exc:  # pragma: no cover - filesystem edge case
        logger.warning("Could not open log file: %s", exc)

    _CONFIGURED = True
    return logger
