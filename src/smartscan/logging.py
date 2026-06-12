"""Logging setup with stderr and optional file output."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


def setup_logging(log_file: str | None = None) -> None:
    """Configure the root logger with stderr output and an optional file handler."""
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(logging.DEBUG)

    debug = os.environ.get("DEBUG", "").lower() in ("1", "true", "yes")
    stderr_level = logging.DEBUG if debug else logging.WARNING
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(stderr_level)
    stderr_handler.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(stderr_handler)

    if log_file:
        _add_file_handler(root, log_file)


def _add_file_handler(root: logging.Logger, log_file: str) -> None:
    try:
        log_path = Path(log_file).expanduser()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(str(log_path))
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(
            logging.Formatter(
                "[%(asctime)s][%(levelname)s] %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%SZ",
            )
        )
        root.addHandler(fh)
    except OSError as exc:
        logging.warning("Cannot create log file %s: %s", log_file, exc)
