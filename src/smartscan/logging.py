"""Logging setup — writes to a log file only, keeping terminal output clean for Rich."""

from __future__ import annotations

import logging
from pathlib import Path


def setup_logging(log_file: str | None = None, log_level: str = "WARNING") -> None:
    """Configure the root logger with a file handler at the given *log_level*.

    No stderr handler is attached — logging output does not compete with
    CLI console output (Rich tables, JSON lines, etc.).

    Replaces any previously attached handler, so it is safe to call more
    than once (e.g. to reconfigure after loading a config file).
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)

    root.setLevel(logging.DEBUG)

    if log_file:
        _add_file_handler(root, log_file, log_level)
    else:
        root.addHandler(logging.NullHandler())


def _add_file_handler(root: logging.Logger, log_file: str, log_level: str) -> None:
    level = getattr(logging, log_level.upper(), logging.WARNING)
    try:
        log_path = Path(log_file).expanduser()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(str(log_path))
        fh.setLevel(level)
        fh.setFormatter(
            logging.Formatter(
                "[%(asctime)s][%(levelname)s] %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%SZ",
            )
        )
        root.addHandler(fh)
    except OSError as exc:
        print(f"Cannot create log file {log_file}: {exc}", flush=True)
        root.addHandler(logging.NullHandler())
