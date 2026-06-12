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
    """Read a TOML configuration file and return a validated :class:`SmartScanConfig`."""
    from .constants import DEFAULT_CONFIG_PATH

    path = config_path or DEFAULT_CONFIG_PATH
    expanded = Path(path).expanduser()
    if not expanded.is_file():
        return SmartScanConfig()

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
