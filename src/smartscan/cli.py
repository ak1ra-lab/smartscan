"""CLI entry point with argparse subcommands for collect and query modes."""

from __future__ import annotations

import argparse
import logging
import sys

from .commands import do_collect, do_query
from .config import load_config
from .constants import DEFAULT_CONFIG_PATH, DEFAULT_DB_PATH, DEFAULT_LOG_FILE
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
        default=DEFAULT_CONFIG_PATH,
        help=f"TOML config file path (default: {DEFAULT_CONFIG_PATH})",
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
        default=cfg.no_save,
        help="Skip saving SMART data to database",
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

    return parser


def main() -> None:
    """Entry point: load config, parse args, and dispatch to the appropriate subcommand."""
    try:
        pre_parser = argparse.ArgumentParser(add_help=False)
        pre_parser.add_argument("--config", default=DEFAULT_CONFIG_PATH)
        pre_args, remaining = pre_parser.parse_known_args()

        config = load_config(pre_args.config)

        parser = _build_parser(config)
        args = parser.parse_args(remaining)

        setup_logging(args.log_file)

        if args.command == "query":
            do_query(args)
        else:
            do_collect(args)
    except SmartScanError as exc:
        logging.error("%s", exc)
        sys.exit(1)
