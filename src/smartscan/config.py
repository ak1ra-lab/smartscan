"""TOML configuration file loading with Pydantic validation."""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path

from pydantic import ValidationError

from .constants import DEFAULT_CONFIG_PATH
from .models import SmartScanConfig


def load_config(config_path: str = DEFAULT_CONFIG_PATH) -> SmartScanConfig:
    """Read a TOML configuration file and return a validated :class:`SmartScanConfig`."""
    expanded = Path(config_path).expanduser()
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

    try:
        return SmartScanConfig.model_validate(raw)
    except ValidationError as exc:
        logging.warning("Invalid config values: %s", exc)
        return SmartScanConfig()
