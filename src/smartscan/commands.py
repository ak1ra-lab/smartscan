"""High-level command implementations for collect and query workflows."""

from __future__ import annotations

import logging
import os
import sqlite3
import sys
import time
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from typing import Any

from .database import init_db, open_db, parse_date, query_smart_info, save_to_db
from .exceptions import DiskNotFoundError
from .llm import call_llm, call_llm_batch
from .notifications import send_notifications
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

DiskEntry = tuple[str, str, Any, list[Alert], dict[str, Any] | None, int, str | None]
#                name  path  fields alerts  data                     rc  llm_analysis


# ── helpers ─────────────────────────────────────────────────────────────


def _build_alerts_text(alerts: list[Alert]) -> str:
    if not alerts:
        return "  (none)"
    return "\n".join(f"  - {a.message}" for a in alerts)


def _collect_disk_data(symlink: Any, args: Namespace) -> DiskEntry:
    disk_name: str = symlink.name
    disk_path: str = os.readlink(symlink)

    data, rc = run_smartctl(symlink)
    if not data:
        return disk_name, disk_path, None, [], None, rc, None

    fields = extract_fields(data)

    alerts: list[Alert] = []
    if args.thresholds_enabled:
        alerts = check_thresholds(fields, args.threshold_rules)

    return disk_name, disk_path, fields, alerts, data, rc, None


def _display_entry(
    disk_name: str,
    disk_path: str,
    fields: Any,
    alerts: list[Alert],
    data: dict[str, Any] | None,
    args: Namespace,
) -> None:
    if args.json:
        assert data is not None  # guaranteed when fields is not None
        print_json_output(disk_name, disk_path, fields, data)
    else:
        print_table(disk_name, fields, alerts, verbose=args.verbose)


def _save_entry(
    conn: sqlite3.Connection | None,
    disk_name: str,
    disk_path: str,
    fields: Any,
    data: dict[str, Any] | None,
    llm_analysis: str | None = None,
) -> None:
    if conn is None or data is None:
        return
    try:
        save_to_db(conn, disk_name, disk_path, fields, data, llm_analysis=llm_analysis)
    except sqlite3.Error as exc:
        logging.error("Failed to save SMART data for %s: %s", disk_name, exc)


def _try_llm_per_disk(
    fields: Any,
    alerts: list[Alert],
    data: dict[str, Any] | None,
    rc: int,
    args: Namespace,
) -> str | None:
    llm_mode = args.llm  # None | "all" | "summary" | "off"

    if llm_mode == "off" or llm_mode == "summary":
        return None

    if llm_mode is None:
        if not args.llm_config.enabled or not alerts:
            return None

    alerts_text = _build_alerts_text(alerts)
    return call_llm(fields, alerts_text, args.llm_config, raw_data=data, returncode=rc)


def _has_any_notifier_channel(notify_config: Any) -> bool:
    return any(
        [
            notify_config.telegram.enabled and notify_config.telegram.bot_token,
            notify_config.dingtalk.enabled and notify_config.dingtalk.webhook_url,
            notify_config.feishu.enabled and notify_config.feishu.webhook_url,
        ]
    )


def _should_notify(args: Namespace, entries: list[DiskEntry]) -> bool:
    if not _has_any_notifier_channel(args.notify_config):
        return False
    if args.notify:
        return True
    return any(alerts for _, _, _, alerts, *_ in entries)


def _maybe_notify(
    args: Namespace,
    entries: list[DiskEntry],
    batch_llm_analysis: str | None = None,
) -> None:
    if not _should_notify(args, entries):
        return
    entries_with_fields = [e for e in entries if e[2] is not None]
    send_notifications(
        args.notify_config,
        entries_with_fields,
        batch_llm_analysis=batch_llm_analysis,
    )


# ── public command implementations ───────────────────────────────────────


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

    entries: list[DiskEntry] = []
    exit_code = 0

    for disk_idx, symlink in enumerate(disks):
        entry = _collect_disk_data(symlink, args)
        entries.append(entry)
        disk_name, disk_path, fields, alerts, data, rc, llm_analysis = entry

        if not fields:
            if rc != 0:
                exit_code = 1
            continue

        _display_entry(disk_name, disk_path, fields, alerts, data, args)

        llm_analysis = _try_llm_per_disk(fields, alerts, data, rc, args)
        if llm_analysis:
            if not args.json:
                print_llm_analysis(llm_analysis)
            if args.llm_config.delay > 0 and disk_idx < len(disks) - 1:
                time.sleep(args.llm_config.delay)
            # write-back into entry for notifications
            entry = (disk_name, disk_path, fields, alerts, data, rc, llm_analysis)
            entries[-1] = entry

        _save_entry(conn, disk_name, disk_path, fields, data, llm_analysis)

    batch_llm_analysis: str | None = None
    if args.llm == "summary":
        valid = [(n, p, f, a, d, rc, la) for n, p, f, a, d, rc, la in entries if f]
        if valid:
            batch_llm_analysis = call_llm_batch(valid, args.llm_config)
            if batch_llm_analysis and not args.json:
                print_llm_analysis(batch_llm_analysis)

    _maybe_notify(args, entries, batch_llm_analysis)

    if conn:
        conn.close()

    sys.exit(exit_code)


def do_query(args: Namespace) -> None:
    last_days = args.last_days
    if last_days is None:
        last_days = args.query_config.last_days

    if last_days:
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
