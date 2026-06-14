"""High-level command implementations for collect and query workflows."""

from __future__ import annotations

import logging
import os
import sqlite3
import sys
import time
from argparse import Namespace
from typing import Any

from .database import init_db, open_db, query_smart_info, save_to_db
from .exceptions import DiskNotFoundError
from .llm import call_llm
from .output import (
    print_json_output,
    print_llm_analysis,
    print_lsblk_json,
    print_lsblk_tree,
    print_query_table,
    print_table,
    row_to_fields,
)
from .smartctl import build_device_tree, extract_fields, find_disks, run_smartctl
from .thresholds import Alert, check_thresholds


def _build_alerts_text(alerts: list[Alert]) -> str:
    if not alerts:
        return "  (none)"
    return "\n".join(f"  - {a.message}" for a in alerts)


def _collect_one_disk(
    disk_idx: int,
    total_disks: int,
    symlink: Any,
    conn: sqlite3.Connection | None,
    args: Namespace,
) -> int:
    disk_name = symlink.name
    disk_path = os.readlink(symlink)

    data, rc = run_smartctl(symlink)
    if not data:
        return rc

    fields = extract_fields(data)

    alerts: list[Alert] = []
    if args.thresholds_enabled:
        alerts = check_thresholds(fields, args.threshold_rules)

    if args.json:
        print_json_output(disk_name, disk_path, fields, data)
    else:
        print_table(disk_name, fields, alerts, verbose=args.verbose)

    llm_analysis = None
    if args.force_llm or (args.llm_config.enabled and alerts):
        alerts_text = _build_alerts_text(alerts)
        llm_analysis = call_llm(fields, alerts_text, args.llm_config, raw_data=data)
    if llm_analysis:
        if not args.json:
            print_llm_analysis(llm_analysis)
        if args.llm_config.delay > 0 and disk_idx < total_disks - 1:
            time.sleep(args.llm_config.delay)

    if conn:
        try:
            save_to_db(
                conn, disk_name, disk_path, fields, data, llm_analysis=llm_analysis
            )
        except sqlite3.Error as exc:
            logging.error("Failed to save SMART data for %s: %s", disk_name, exc)

    return rc


def do_lsblk(args: Namespace) -> None:
    from .smartctl import _SOURCE_DIRS

    config_cfg = args.lsblk_config

    sources_list = list(config_cfg.source or _SOURCE_DIRS)
    if args.lsblk_source:
        sources_list.extend(args.lsblk_source)
    sources = tuple(sources_list)

    try:
        devices = build_device_tree(
            args.pattern,
            sources=sources,
            exclude_patterns=args.exclude_patterns or None,
        )
    except DiskNotFoundError as exc:
        logging.error("%s", exc)
        sys.exit(1)

    if args.json:
        print_lsblk_json(devices)
    else:
        print_lsblk_tree(devices)


def do_collect(args: Namespace) -> None:
    if os.geteuid() != 0:
        logging.warning(
            "This program typically requires root privileges to access SMART data."
        )

    conn = None
    if not args.no_save:
        try:
            conn = init_db(args.db_path)
        except OSError as exc:
            logging.error("Failed to open database at %s: %s", args.db_path, exc)

    try:
        disks = find_disks(args.pattern, exclude_patterns=args.exclude_patterns or None)
    except DiskNotFoundError as exc:
        logging.error("%s", exc)
        sys.exit(1)

    exit_code = 0
    for disk_idx, symlink in enumerate(disks):
        rc = _collect_one_disk(disk_idx, len(disks), symlink, conn, args)
        if rc != 0:
            exit_code = 1

    if conn:
        conn.close()

    sys.exit(exit_code)


def do_query(args: Namespace) -> None:
    from .database import parse_date

    last_days = args.last_days
    if last_days is None:
        last_days = args.query_config.last_days

    if last_days:
        from datetime import datetime, timedelta, timezone

        since_str = (datetime.now(timezone.utc) - timedelta(days=last_days)).strftime(
            "%Y-%m-%d"
        )
    else:
        since_str = args.since or args.query_config.since

    until_str = args.until or args.query_config.until

    since = parse_date(since_str) if since_str else None
    until = parse_date(until_str) if until_str else None

    conn = open_db(args.db_path)
    if conn is None:
        sys.exit(0)

    try:
        rows = query_smart_info(conn, args.pattern, since, until)
    except sqlite3.OperationalError as exc:
        logging.error("Query failed: %s", exc)
        conn.close()
        sys.exit(1)

    if not rows:
        logging.info("No SMART records found matching the query.")
        conn.close()
        sys.exit(0)

    for row in rows:
        fields = row_to_fields(row)

        alerts = []
        if args.thresholds_enabled:
            alerts = check_thresholds(fields, args.threshold_rules)

        if args.json:
            llm_col = row["llm_analysis"] if "llm_analysis" in row.keys() else None
            print_json_output(
                row["disk_name"],
                row["disk_path"],
                fields,
                timestamp=row["timestamp"],
                llm_analysis=llm_col,
            )
        else:
            print_query_table(
                row["disk_name"],
                row["disk_path"],
                row["timestamp"],
                fields,
                alerts=alerts,
                verbose=args.verbose,
            )

    conn.close()
