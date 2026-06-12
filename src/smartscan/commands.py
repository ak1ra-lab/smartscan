"""High-level command implementations for collect and query workflows."""

from __future__ import annotations

import logging
import os
import sqlite3
import sys
from argparse import Namespace

from .database import init_db, open_db, query_smart_info, save_to_db
from .exceptions import DiskNotFoundError
from .llm import call_llm
from .output import (
    print_json_output,
    print_llm_analysis,
    print_query_table,
    print_table,
    row_to_fields,
)
from .smartctl import extract_fields, find_disks, run_smartctl
from .thresholds import check_thresholds


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
        disks = find_disks(args.pattern)
    except DiskNotFoundError as exc:
        logging.error("%s", exc)
        sys.exit(1)

    thresholds_enabled = args.thresholds_enabled
    llm_enabled = args.llm_enabled and not args.no_llm

    exit_code = 0
    for symlink in disks:
        disk_name = symlink.name
        disk_path = os.readlink(symlink)

        data, rc = run_smartctl(symlink)
        if rc != 0:
            exit_code = 1

        if not data:
            continue

        fields = extract_fields(data)

        alerts = []
        if thresholds_enabled:
            alerts = check_thresholds(fields, args.threshold_rules)

        if args.json:
            print_json_output(disk_name, disk_path, fields, data)
        else:
            print_table(disk_name, fields, alerts, verbose=args.verbose)

        llm_analysis = None
        if llm_enabled and alerts:
            alerts_text = "\n".join(f"  - {a.message}" for a in alerts)
            llm_analysis = call_llm(fields, alerts_text, args.llm_config)
            if llm_analysis:
                if not args.json:
                    print_llm_analysis(llm_analysis)

        if conn:
            try:
                save_to_db(
                    conn, disk_name, disk_path, fields, data, llm_analysis=llm_analysis
                )
            except sqlite3.Error as exc:
                logging.error("Failed to save SMART data for %s: %s", disk_name, exc)

    if conn:
        conn.close()

    sys.exit(exit_code)


def do_query(args: Namespace) -> None:
    from .database import parse_date

    since = parse_date(args.since) if args.since else None
    until = parse_date(args.until) if args.until else None

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
                verbose=args.verbose,
            )

    conn.close()
