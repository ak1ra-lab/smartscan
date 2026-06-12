"""SQLite database operations: init, save, query for SMART history."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import DB_MIGRATIONS, DB_SCHEMA
from .exceptions import InvalidDateError
from .models import SmartInfo


def _run_migrations(conn: sqlite3.Connection) -> None:
    for sql in DB_MIGRATIONS:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            pass  # column already exists


def init_db(db_path: str) -> sqlite3.Connection:
    """Create or open the SQLite database, applying the schema and enabling WAL mode."""
    expanded = Path(db_path).expanduser()
    expanded.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(expanded))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(DB_SCHEMA)
    _run_migrations(conn)
    return conn


def open_db(db_path: str) -> sqlite3.Connection | None:
    """Open the database in read-only mode for querying, returning ``None`` if it doesn't exist."""
    expanded = Path(db_path).expanduser()
    if not expanded.is_file():
        logging.warning("Database not found: %s", expanded)
        return None
    conn = sqlite3.connect(f"file:{expanded}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def register_regexp(conn: sqlite3.Connection) -> None:
    def _regexp(pattern: str, value: str | None) -> bool:
        if value is None:
            return False
        return bool(re.search(pattern, value))

    conn.create_function("REGEXP", 2, _regexp)


def parse_date(date_str: str) -> datetime:
    """Parse a ``YYYY-MM-DD`` date string into a UTC-aware datetime.

    Raises:
        InvalidDateError: If the string does not match the expected format.
    """
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise InvalidDateError(
            f"Invalid date format: {date_str} (expected YYYY-MM-DD)"
        ) from exc


def query_smart_info(
    conn: sqlite3.Connection,
    pattern: str | None,
    since: datetime | None,
    until: datetime | None,
) -> list[sqlite3.Row]:
    """Query historical SMART records with optional disk name regex and date range filters."""
    register_regexp(conn)

    conditions: list[str] = []
    params: list[str] = []

    if pattern:
        conditions.append("disk_name REGEXP ?")
        params.append(pattern)

    if since:
        conditions.append("timestamp >= ?")
        params.append(since.strftime("%Y-%m-%dT00:00:00Z"))

    if until:
        conditions.append("timestamp <= ?")
        params.append(until.strftime("%Y-%m-%dT23:59:59Z"))

    where = " AND ".join(conditions) if conditions else "1=1"
    sql = f"SELECT * FROM smart_info WHERE {where} ORDER BY disk_path, timestamp"

    logging.debug("Query: %s  params: %s", sql, params)
    return conn.execute(sql, params).fetchall()


_COLUMNS_INSERT = (
    "timestamp",
    "disk_name",
    "disk_path",
    "model_family",
    "model_name",
    "serial_number",
    "firmware_version",
    "user_capacity_bytes",
    "user_capacity_gib",
    "rotation_rate",
    "interface_speed",
    "power_on_time_hours",
    "power_cycle_count",
    "smart_status",
    "temperature_celsius",
    "reallocated_sector_ct",
    "current_pending_sector",
    "offline_uncorrectable",
    "reallocated_event_count",
    "ata_smart_error_log_count",
    "self_test_status",
    "udma_crc_error_count",
    "raw_read_error_rate",
    "spin_retry_count",
    "power_off_retract_count",
    "load_cycle_count",
    "helium_level",
    "raw_json",
    "llm_analysis",
)


def save_to_db(
    conn: sqlite3.Connection,
    disk_name: str,
    disk_path: str,
    fields: SmartInfo,
    raw_data: dict[str, Any],
    llm_analysis: str | None = None,
) -> None:
    """Persist a single SMART data record into the database."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    placeholders = ", ".join("?" * len(_COLUMNS_INSERT))
    columns = ", ".join(_COLUMNS_INSERT)
    conn.execute(
        f"INSERT INTO smart_info ({columns}) VALUES ({placeholders})",
        (
            timestamp,
            disk_name,
            disk_path,
            fields["model_family"],
            fields["model_name"],
            fields["serial_number"],
            fields["firmware_version"],
            fields["user_capacity_bytes"],
            fields["user_capacity_gib"],
            fields["rotation_rate"],
            fields["interface_speed"],
            fields["power_on_time"],
            fields["power_cycle_count"],
            fields["smart_status"],
            fields["temperature"],
            fields["reallocated_sector_ct"],
            fields["current_pending_sector"],
            fields["offline_uncorrectable"],
            fields["reallocated_event_count"],
            fields["ata_smart_error_log"],
            fields["self_test_status"],
            fields["udma_crc_error_count"],
            fields["raw_read_error_rate"],
            fields["spin_retry_count"],
            fields["power_off_retract_count"],
            fields["load_cycle_count"],
            fields["helium_level"],
            json.dumps(raw_data, ensure_ascii=False),
            llm_analysis,
        ),
    )
    conn.commit()
