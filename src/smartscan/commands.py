"""High-level command implementations for collect and query workflows."""

from __future__ import annotations

import logging
import os
import sqlite3
import sys
import time
from argparse import Namespace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .database import init_db, open_db, parse_date, query_smart_info, save_to_db
from .dedup import compact_by_disk, find_redundant_ids
from .exceptions import DatabaseError
from .llm import call_llm, call_llm_batch, call_llm_trend
from .models import NotificationConfig, SmartInfo
from .notifications import send_notifications
from .output import (
    console,
    print_json_output,
    print_llm_analysis,
    print_lsblk_json,
    print_lsblk_tree,
    print_query_table,
    print_table,
    row_to_fields,
)
from .results import DiskEntry
from .smartctl import (
    SOURCE_DIRS,
    build_device_tree,
    extract_fields,
    find_disks,
    run_smartctl,
)
from .thresholds import Alert, check_thresholds

_PRUNE_CHUNK = 500


# ── helpers ─────────────────────────────────────────────────────────────


def _build_alerts_text(alerts: list[Alert]) -> str:
    if not alerts:
        return "  (none)"
    return "\n".join(f"  - {a.message}" for a in alerts)


def _collect_disk_data(symlink: Path, args: Namespace) -> DiskEntry:
    disk_name = symlink.name
    disk_path = os.readlink(symlink)

    logging.debug("Collecting SMART data from %s (%s)", disk_name, disk_path)
    data, rc = run_smartctl(symlink)
    if not data:
        logging.debug("No SMART data returned for %s (rc=%d)", disk_name, rc)
        return DiskEntry(disk_name, disk_path, None, [], None, rc)

    fields = extract_fields(data)
    logging.debug("Extracted %d fields for %s", len(fields), disk_name)

    alerts: list[Alert] = []
    if args.thresholds_enabled:
        alerts = check_thresholds(fields, args.threshold_rules)
        if alerts:
            logging.debug(
                "%d alert(s) triggered for %s: %s",
                len(alerts),
                disk_name,
                [a.field for a in alerts],
            )

    return DiskEntry(disk_name, disk_path, fields, alerts, data, rc)


def _display_entry(entry: DiskEntry, args: Namespace) -> None:
    if entry.fields is None:
        return
    if args.json:
        print_json_output(entry.disk_name, entry.disk_path, entry.fields)
    else:
        print_table(
            entry.disk_name,
            entry.fields,
            entry.alerts,
            verbose=args.verbose,
        )


def _save_entry(conn: sqlite3.Connection | None, entry: DiskEntry) -> None:
    if conn is None or entry.fields is None or entry.data is None:
        return
    try:
        save_to_db(
            conn,
            entry.disk_name,
            entry.disk_path,
            entry.fields,
            entry.data,
            llm_analysis=entry.llm_analysis,
        )
        logging.debug("Saved SMART data to DB for %s", entry.disk_name)
    except sqlite3.Error as exc:
        logging.error("Failed to save SMART data for %s: %s", entry.disk_name, exc)


def _try_llm_per_disk(entry: DiskEntry, args: Namespace) -> str | None:
    llm_mode = args.llm  # None | "all" | "summary" | "off"

    if llm_mode in ("off", "summary"):
        logging.debug("LLM skipped (mode=%s)", llm_mode or "default")
        return None

    if llm_mode is None:
        if not args.llm_config.enabled:
            logging.debug("LLM skipped (llm.enabled=false)")
            return None
        if not entry.alerts:
            logging.debug("LLM skipped (no alerts)")
            return None

    if entry.fields is None:
        return None

    logging.debug("Calling per-disk LLM (mode=%s)", llm_mode or "default")
    alerts_text = _build_alerts_text(entry.alerts)
    return call_llm(
        entry.fields,
        alerts_text,
        args.llm_config,
        raw_data=entry.data,
        returncode=entry.returncode,
    )


def _has_any_notifier_channel(notify_config: NotificationConfig) -> bool:
    return bool(
        (notify_config.telegram.enabled and notify_config.telegram.bot_token)
        or (notify_config.dingtalk.enabled and notify_config.dingtalk.webhook_url)
        or (notify_config.feishu.enabled and notify_config.feishu.webhook_url)
    )


def _should_notify(args: Namespace, entries: list[DiskEntry]) -> bool:
    if not _has_any_notifier_channel(args.notify_config):
        logging.debug("Notify skipped: no channels configured")
        return False
    if args.notify:
        logging.debug("Notify triggered: --notify flag")
        return True
    triggered = any(entry.alerts for entry in entries)
    if triggered:
        logging.debug("Notify triggered: alerts present")
    else:
        logging.debug("Notify skipped: no alerts and --notify not set")
    return triggered


def _maybe_notify(
    args: Namespace,
    entries: list[DiskEntry],
    batch_llm_analysis: str | None = None,
) -> None:
    if not _should_notify(args, entries):
        return
    entries_with_fields = [e for e in entries if e.fields is not None]
    logging.debug("Dispatching notifications for %d disk(s)", len(entries_with_fields))
    send_notifications(
        args.notify_config,
        entries_with_fields,
        batch_llm_analysis=batch_llm_analysis,
    )


# ── public command implementations ───────────────────────────────────────


def do_lsblk(args: Namespace) -> None:
    config_cfg = args.lsblk_config

    sources_list = list(config_cfg.source or SOURCE_DIRS)
    if args.lsblk_source:
        sources_list.extend(args.lsblk_source)
    sources = tuple(sources_list)

    devices = build_device_tree(
        args.pattern,
        sources=sources,
        exclude_patterns=args.exclude_patterns or None,
    )

    if args.json:
        print_lsblk_json(devices)
    else:
        print_lsblk_tree(devices)


def do_collect(args: Namespace) -> int:
    if os.geteuid() != 0:
        logging.warning("This program typically requires root privileges to access SMART data.")

    logging.debug(
        "collect: pattern=%r llm=%s notify=%s no_save=%s",
        args.pattern,
        args.llm or "default",
        args.notify,
        args.no_save,
    )

    conn = None
    if not args.no_save:
        try:
            conn = init_db(args.db_path)
            logging.debug("Database opened at %s", args.db_path)
        except (OSError, sqlite3.Error) as exc:
            print(
                f"Error: Failed to open database at {args.db_path}: {exc}",
                file=sys.stderr,
            )

    disks = find_disks(args.pattern, exclude_patterns=args.exclude_patterns or None)
    logging.info("Collecting SMART data from %d disk(s)", len(disks))

    entries: list[DiskEntry] = []
    exit_code = 0

    for disk_idx, symlink in enumerate(disks):
        entry = _collect_disk_data(symlink, args)
        entries.append(entry)

        if entry.fields is None:
            if entry.returncode != 0:
                exit_code = 1
            continue

        _display_entry(entry, args)

        entry.llm_analysis = _try_llm_per_disk(entry, args)
        if entry.llm_analysis:
            if not args.json:
                print_llm_analysis(entry.llm_analysis)
            if args.llm_config.delay > 0 and disk_idx < len(disks) - 1:
                logging.debug("Sleeping %.1fs before next LLM call", args.llm_config.delay)
                time.sleep(args.llm_config.delay)

        _save_entry(conn, entry)

    batch_llm_analysis: str | None = None
    if args.llm == "summary":
        valid = [entry for entry in entries if entry.fields is not None]
        if valid:
            logging.info("Running batch LLM analysis on %d disk(s)", len(valid))
            batch_llm_analysis = call_llm_batch(valid, args.llm_config)
            if batch_llm_analysis and not args.json:
                print_llm_analysis(batch_llm_analysis)
        else:
            logging.debug("Batch LLM skipped: no valid disk data")

    _maybe_notify(args, entries, batch_llm_analysis)

    if conn is not None:
        conn.close()

    logging.debug("collect: done (exit_code=%d)", exit_code)
    return exit_code


def do_query(args: Namespace) -> None:
    last_days = args.last_days
    if last_days is None:
        last_days = args.query_config.last_days

    if last_days:
        since_str = (datetime.now(UTC) - timedelta(days=last_days)).strftime("%Y-%m-%d")
    else:
        since_str = args.since or args.query_config.since

    until_str = args.until or args.query_config.until

    compact_enabled = not args.no_compact

    logging.debug(
        "query: pattern=%r last_days=%s since=%s until=%s compact=%s window=%s",
        args.pattern,
        last_days,
        since_str,
        until_str,
        compact_enabled,
        args.compact_window,
    )

    since = parse_date(since_str) if since_str else None
    until = parse_date(until_str) if until_str else None

    try:
        conn = open_db(args.db_path)
    except sqlite3.Error as exc:
        raise DatabaseError(f"Failed to open database at {args.db_path}: {exc}") from exc
    if conn is None:
        print(f"Database not found: {args.db_path}", file=sys.stderr)
        return

    try:
        rows = query_smart_info(conn, args.pattern, since, until)
    except sqlite3.OperationalError as exc:
        conn.close()
        raise DatabaseError(f"Query failed: {exc}") from exc

    logging.info("Query returned %d record(s)", len(rows))

    if compact_enabled and rows:
        compacted = compact_by_disk(rows, args.compact_window)
        logging.info("Compacted %d -> %d record(s)", len(rows), len(compacted))
        rows = compacted

    if args.trend and rows and args.llm_config.enabled:
        trend_groups: dict[str, list[tuple[str, SmartInfo]]] = {}
        disk_name_map: dict[str, str] = {}
        for row in rows:
            disk_path = row["disk_path"]
            trend_groups.setdefault(disk_path, []).append((row["timestamp"], row_to_fields(row)))
            disk_name_map.setdefault(disk_path, row["disk_name"])
        for disk_path, entries in trend_groups.items():
            if len(entries) < 2:
                continue
            disk_name = disk_name_map[disk_path]
            logging.info(
                "Requesting trend analysis for %s (%d entries)",
                disk_name,
                len(entries),
            )
            analysis = call_llm_trend(disk_name, disk_path, entries, args.llm_config)
            if analysis and not args.json:
                console.rule(f"[bold]Trend Analysis: {disk_name} ({disk_path})[/bold]")
                print_llm_analysis(analysis)

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


def do_prune(args: Namespace) -> None:
    window = args.prune_window
    logging.debug(
        "prune: pattern=%r window=%dmin force=%s dry_run=%s",
        args.pattern,
        window,
        args.force,
        args.dry_run,
    )

    db_path = Path(args.db_path).expanduser()
    if not db_path.is_file():
        raise DatabaseError(f"Database not found at {args.db_path}")

    try:
        conn = init_db(args.db_path)
    except (OSError, sqlite3.Error) as exc:
        raise DatabaseError(f"Failed to open database at {args.db_path}: {exc}") from exc

    try:
        try:
            redundant_ids = find_redundant_ids(conn, args.pattern, window)
        except sqlite3.OperationalError as exc:
            raise DatabaseError(f"Prune analysis failed: {exc}") from exc

        if not redundant_ids:
            print("No redundant records found to prune.")
            return

        print(f"Found {len(redundant_ids)} redundant record(s) (window={window}min, pattern={args.pattern!r}).")

        if args.dry_run:
            return

        if not args.force:
            try:
                answer = input("Delete these records? [y/N] ")
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if answer.strip().lower() not in ("y", "yes"):
                print("Prune cancelled.")
                return

        try:
            deleted = 0
            for i in range(0, len(redundant_ids), _PRUNE_CHUNK):
                chunk = redundant_ids[i : i + _PRUNE_CHUNK]
                placeholders = ", ".join("?" * len(chunk))
                conn.execute(
                    f"DELETE FROM smart_info WHERE id IN ({placeholders})",
                    chunk,
                )
                deleted += len(chunk)
            conn.commit()
        except sqlite3.OperationalError as exc:
            raise DatabaseError(f"Prune failed: {exc}") from exc

        logging.info("Pruned %d redundant record(s)", deleted)
        print(f"Pruned {deleted} redundant record(s).")
    finally:
        conn.close()
