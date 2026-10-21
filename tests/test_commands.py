"""Tests for command functions outside the CLI parser."""

from __future__ import annotations

from argparse import Namespace

import pytest

from smartscan.commands import do_prune, do_query
from smartscan.exceptions import DatabaseError
from smartscan.models import LLMConfig, QueryConfig, ThresholdRules


def test_prune_missing_database_raises(tmp_path) -> None:
    args = Namespace(
        pattern=".*",
        prune_window=30,
        force=False,
        dry_run=False,
        db_path=str(tmp_path / "missing.db"),
    )

    with pytest.raises(DatabaseError, match="Database not found"):
        do_prune(args)


def test_query_missing_database_reports_error(tmp_path, capsys) -> None:
    args = Namespace(
        last_days=None,
        query_config=QueryConfig(),
        since=None,
        until=None,
        no_compact=False,
        compact_window=30,
        pattern=".*",
        db_path=str(tmp_path / "missing.db"),
        trend=False,
        llm_config=LLMConfig(),
        thresholds_enabled=False,
        threshold_rules=ThresholdRules(),
        json=False,
        verbose=False,
    )

    assert do_query(args) is None

    captured = capsys.readouterr()
    assert "Database not found" in captured.err
