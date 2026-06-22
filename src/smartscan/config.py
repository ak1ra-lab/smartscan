"""TOML configuration file loading with Pydantic validation."""

from __future__ import annotations

import logging
import os
import re
import tomllib
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .models import SmartScanConfig

_ENV_VAR_RE = re.compile(r"\$\{(\w+)\}")


def _expand_env_vars(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _expand_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env_vars(v) for v in obj]
    if isinstance(obj, str):
        return _ENV_VAR_RE.sub(lambda m: os.environ.get(m.group(1), ""), obj)
    return obj


def load_config(config_path: str | None = None) -> SmartScanConfig:
    """Read a TOML configuration file and return a validated :class:`SmartScanConfig`.

    When *config_path* is given, only that file is tried.
    When *config_path* is ``None``, the first file found among ``CONFIG_SEARCH_PATHS`` is used.
    If no config file exists, a default :class:`SmartScanConfig` is returned.
    """
    from .constants import CONFIG_SEARCH_PATHS

    candidates: list[Path]
    if config_path is not None:
        candidates = [Path(config_path).expanduser()]
    else:
        candidates = [Path(p).expanduser() for p in CONFIG_SEARCH_PATHS]

    expanded = None
    for candidate in candidates:
        if candidate.is_file():
            expanded = candidate
            break

    if expanded is None:
        logging.debug("No config file found, using defaults")
        return SmartScanConfig()

    logging.debug("Loading config from %s", expanded)

    try:
        raw = tomllib.loads(expanded.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        logging.warning("Failed to parse config file %s: %s", expanded, exc)
        return SmartScanConfig()

    if not isinstance(raw, dict):
        logging.warning("Invalid config file format; expected a TOML table.")
        return SmartScanConfig()

    raw = _expand_env_vars(raw)

    try:
        return SmartScanConfig.model_validate(raw)
    except ValidationError as exc:
        logging.warning("Invalid config values: %s", exc)
        return SmartScanConfig()
