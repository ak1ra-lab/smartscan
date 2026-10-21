"""Tests for TOML configuration loading and validation."""

from __future__ import annotations

import pytest

from smartscan.config import load_config
from smartscan.exceptions import ConfigError


def test_missing_explicit_config_raises(tmp_path) -> None:
    with pytest.raises(ConfigError, match="Config file not found"):
        load_config(str(tmp_path / "missing.toml"))


def test_invalid_toml_raises(tmp_path) -> None:
    path = tmp_path / "bad.toml"
    path.write_text("not = [valid", encoding="utf-8")

    with pytest.raises(ConfigError, match="Failed to read config file"):
        load_config(str(path))


def test_invalid_values_raise(tmp_path) -> None:
    path = tmp_path / "bad.toml"
    path.write_text("[thresholds]\ntemperature_celsius = 'hot'\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="Invalid config values"):
        load_config(str(path))


def test_invalid_lsblk_source_raises(tmp_path) -> None:
    path = tmp_path / "bad.toml"
    path.write_text("[lsblk]\nsource = ['bogus']\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="Invalid config values"):
        load_config(str(path))


def test_valid_config_loads(tmp_path) -> None:
    path = tmp_path / "ok.toml"
    path.write_text('[llm]\nlang = "zh"\n[lsblk]\nsource = ["by-id"]\n')

    config = load_config(str(path))

    assert config.llm.lang == "zh"
    assert config.lsblk.source == ["by-id"]


def test_no_config_uses_defaults(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "smartscan.constants.CONFIG_SEARCH_PATHS",
        (str(tmp_path / "missing.toml"),),
    )

    config = load_config()

    assert config.format == "table"
    assert config.llm.max_tokens == 8192
