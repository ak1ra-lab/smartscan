"""High-level command implementations for collect and query workflows."""

from __future__ import annotations

import logging
import os
import sqlite3
import sys
from argparse import Namespace

from .database import init_db, open_db, query_smart_info, save_to_db
from .exceptions import DiskNotFoundError
from .output import print_json_output, print_query_table, print_table, row_to_fields
from .smartctl import extract_fields, find_disks, run_smartctl


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

        if args.json:
            print_json_output(disk_name, disk_path, fields, data)
        else:
            print_table(disk_name, fields)

        if conn:
            try:
                save_to_db(conn, disk_name, disk_path, fields, data)
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
            print_json_output(
                row["disk_name"],
                row["disk_path"],
                fields,
                timestamp=row["timestamp"],
            )
        else:
            print_query_table(
                row["disk_name"],
                row["disk_path"],
                row["timestamp"],
                fields,
            )

    conn.close()
