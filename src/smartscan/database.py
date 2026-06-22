"""SQLite database operations: init, save, query for SMART history."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import DB_MIGRATIONS
from .exceptions import InvalidDateError
from .fields import ALL_HEALTH_FIELDS, get_field
from .models import SmartInfo


def _build_schema() -> str:
    col_defs = [
        "    id INTEGER PRIMARY KEY AUTOINCREMENT",
        "    timestamp TEXT NOT NULL",
        "    disk_name TEXT NOT NULL",
        "    disk_path TEXT NOT NULL",
    ]
    for f in ALL_HEALTH_FIELDS:
        col_defs.append(f"    {f.db_column} {f.db_type}")
    col_defs.append("    raw_json TEXT")
    col_defs.append("    llm_analysis TEXT")
    cols = ",\n".join(col_defs)
    return (
        f"CREATE TABLE IF NOT EXISTS smart_info (\n{cols}\n);\n"
        "CREATE INDEX IF NOT EXISTS idx_smart_info_disk_ts\n"
        "    ON smart_info(disk_path, timestamp);"
    )


DB_SCHEMA = _build_schema()


def _run_migrations(conn: sqlite3.Connection) -> None:
    for sql in DB_MIGRATIONS:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError as exc:
            if "duplicate column" not in str(exc):
                logging.warning("Migration failed: %s", exc)


def init_db(db_path: str) -> sqlite3.Connection:
    """Create or open the SQLite database, applying the schema and enabling WAL mode."""
    expanded = Path(db_path).expanduser()
    expanded.parent.mkdir(parents=True, exist_ok=True)
    logging.debug("Initializing database at %s", expanded)
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
    *(f.db_column for f in ALL_HEALTH_FIELDS),
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
            *(get_field(fields, f.key) for f in ALL_HEALTH_FIELDS),
            json.dumps(raw_data, ensure_ascii=False),
            llm_analysis,
        ),
    )
    conn.commit()
    logging.debug("Saved record for %s at %s", disk_name, timestamp)
