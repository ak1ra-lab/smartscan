# PYTHON_ARGCOMPLETE_OK

"""CLI entry point with argparse subcommands for collect and query modes."""

from __future__ import annotations

import argparse
import logging
import sys

import argcomplete

from .commands import do_collect, do_lsblk, do_query
from .config import load_config
from .constants import DEFAULT_DB_PATH, DEFAULT_LOG_FILE
from .exceptions import SmartScanError
from .logging import setup_logging
from .models import SmartScanConfig


def create_parser() -> argparse.ArgumentParser:
    """Build the argument parser for argcomplete integration, without config defaults."""
    return _build_parser()


def _build_parser(config: SmartScanConfig | None = None) -> argparse.ArgumentParser:
    """Build the argument parser with config-driven defaults."""
    cfg = config or SmartScanConfig()

    parser = argparse.ArgumentParser(
        description="Extract and display important SMART information from disk devices.",
    )

    parser.add_argument(
        "--config",
        default=None,
        help="TOML config file path "
        "(searches ~/.config/smartscan/smartscan.toml then "
        "/etc/smartscan/smartscan.toml when not specified)",
    )
    parser.add_argument(
        "--db-path",
        default=cfg.db_path,
        help=f"Database file path (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--log-file",
        default=cfg.log_file,
        help=f"Log file path (default: {DEFAULT_LOG_FILE})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=cfg.format == "json",
        help="Output as JSON lines instead of table format",
    )
    parser.add_argument(
        "--exclude",
        dest="exclude_patterns",
        action="append",
        metavar="PATTERN",
        default=cfg.exclude_patterns,
        help="Regex patterns to exclude disk devices by symlink name or resolved path "
        "(may be repeated; appended to config exclude_patterns)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    collect_parser = sub.add_parser(
        "collect", help="Collect SMART data from disk devices"
    )
    collect_parser.add_argument(
        "pattern",
        nargs="?",
        default=".*",
        help="Regex pattern to filter disk devices",
    )
    collect_parser.add_argument(
        "--no-save",
        action="store_true",
        default=cfg.collect.no_save,
        help="Skip saving SMART data to database",
    )
    collect_parser.add_argument(
        "--llm",
        choices=["all", "summary", "off"],
        default=None,
        help="LLM analysis mode: 'all' forces per-disk analysis on every disk, "
        "'summary' submits all results as a single batch, "
        "'off' skips LLM entirely "
        "(default: config-driven, per-disk analysis only for disks with alerts)",
    )
    collect_parser.add_argument(
        "--notify",
        action="store_true",
        help="Force sending notifications via configured channels, "
        "even when no alerts are triggered",
    )
    collect_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show extended fields in terminal output",
    )

    query_parser = sub.add_parser(
        "query", help="Query historical SMART data from database"
    )
    query_parser.add_argument(
        "pattern",
        nargs="?",
        default=".*",
        help="Regex pattern to filter disk_name",
    )
    query_parser.add_argument(
        "--since",
        metavar="DATE",
        help="Start date (YYYY-MM-DD) for query",
    )
    query_parser.add_argument(
        "--until",
        metavar="DATE",
        help="End date (YYYY-MM-DD) for query",
    )
    query_parser.add_argument(
        "--last-days",
        type=int,
        metavar="N",
        help="Show records from the last N days (overrides --since)",
    )
    query_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show extended fields in terminal output",
    )

    lsblk_parser = sub.add_parser(
        "lsblk",
        help="Map disk devices to their /dev/disk identifiers",
    )
    lsblk_parser.add_argument(
        "pattern",
        nargs="?",
        default=".*",
        help="Regex pattern to filter identifier names",
    )
    lsblk_parser.add_argument(
        "--source",
        dest="lsblk_source",
        action="append",
        choices=["by-id", "by-path", "by-diskseq"],
        default=None,
        help="Restrict to specific /dev/disk/ source directories "
        "(appended to lsblk.source config; may be repeated; default: all)",
    )

    argcomplete.autocomplete(parser)
    return parser


def main() -> None:
    """Entry point: load config, parse args, and dispatch to the appropriate subcommand."""
    try:
        pre_parser = argparse.ArgumentParser(add_help=False)
        pre_parser.add_argument("--config", default=None)
        pre_args, remaining = pre_parser.parse_known_args()

        config = load_config(pre_args.config)

        parser = _build_parser(config)
        args = parser.parse_args(remaining)

        setup_logging(args.log_file)

        args.thresholds_enabled = config.thresholds.enabled
        args.threshold_rules = config.thresholds
        args.llm_config = config.llm
        args.notify_config = config.notify
        args.collect_config = config.collect
        args.query_config = config.query
        args.lsblk_config = config.lsblk

        if args.command == "query":
            do_query(args)
        elif args.command == "lsblk":
            do_lsblk(args)
        else:
            do_collect(args)
    except SmartScanError as exc:
        logging.error("%s", exc)
        sys.exit(1)
