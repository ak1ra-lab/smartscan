"""TOML configuration file loading with Pydantic validation."""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path

from pydantic import ValidationError

from .exceptions import ConfigError
from .models import SmartScanConfig
from .utils import expand_env_vars


def load_config(config_path: str | None = None) -> SmartScanConfig:
    """Read a TOML configuration file and return a validated :class:`SmartScanConfig`.

    When *config_path* is given, only that file is tried.
    When *config_path* is ``None``, the first file found among ``CONFIG_SEARCH_PATHS`` is used.
    If no config file exists, a default :class:`SmartScanConfig` is returned.
    """
    from .constants import CONFIG_SEARCH_PATHS

    if config_path is not None:
        candidates = [Path(config_path).expanduser()]
    else:
        candidates = [Path(p).expanduser() for p in CONFIG_SEARCH_PATHS]

    expanded = next((c for c in candidates if c.is_file()), None)
    if expanded is None:
        if config_path is not None:
            raise ConfigError(f"Config file not found: {config_path}")
        logging.debug("No config file found, using defaults")
        return SmartScanConfig()

    logging.debug("Loading config from %s", expanded)

    try:
        raw = tomllib.loads(expanded.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"Failed to read config file {expanded}: {exc}") from exc

    try:
        return SmartScanConfig.model_validate(expand_env_vars(raw))
    except ValidationError as exc:
        raise ConfigError(f"Invalid config values in {expanded}: {exc}") from exc
