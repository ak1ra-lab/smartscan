"""Record deduplication: detect significant changes and compact/prune records.

Shared logic used by both ``query --no-compact`` (default is compacted) and
the ``prune`` subcommand.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone

from .database import query_smart_info
from .fields import MONITORED_FIELDS
from .models import SmartInfo
from .output import row_to_fields

_TEMP_DELTA_THRESHOLD: float = 3.0


def _parse_ts(ts_str: str) -> datetime:
    return datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _float_val(value: str) -> float | None:
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _field_changed(prev: SmartInfo, curr: SmartInfo, key: str) -> bool:
    prev_val = str(prev.get(key, ""))
    curr_val = str(curr.get(key, ""))

    if key == "temperature":
        prev_f = _float_val(prev_val)
        curr_f = _float_val(curr_val)
        if prev_f is not None and curr_f is not None:
            return abs(curr_f - prev_f) > _TEMP_DELTA_THRESHOLD

    return prev_val != curr_val


def has_significant_change(prev: SmartInfo, curr: SmartInfo) -> bool:
    return any(_field_changed(prev, curr, key) for key in MONITORED_FIELDS)


def compact_rows(
    rows: list[sqlite3.Row],
    window_minutes: int,
) -> list[sqlite3.Row]:
    if len(rows) <= 1:
        return list(rows)

    prev_fields: SmartInfo | None = None
    keep: list[sqlite3.Row] = []
    cluster_size = 1
    last_kept = rows[0]

    for row in rows[1:]:
        ts_curr = _parse_ts(row["timestamp"])
        ts_ref = _parse_ts(last_kept["timestamp"])
        within_window = (ts_curr - ts_ref) <= timedelta(minutes=window_minutes)

        if prev_fields is None:
            prev_fields = row_to_fields(last_kept)

        curr_fields = row_to_fields(row)

        if within_window and not has_significant_change(prev_fields, curr_fields):
            last_kept = row
            prev_fields = curr_fields
            cluster_size += 1
        else:
            keep.append(last_kept)
            last_kept = row
            prev_fields = curr_fields
            cluster_size = 1

    if last_kept is not None:
        keep.append(last_kept)

    logging.debug(
        "compact_rows: %d -> %d rows (window=%dmin)",
        len(rows),
        len(keep),
        window_minutes,
    )
    return keep


def find_redundant_ids(
    conn: sqlite3.Connection,
    pattern: str,
    window_minutes: int,
) -> list[int]:
    rows = query_smart_info(conn, pattern, None, None)

    if not rows:
        return []

    groups: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        groups.setdefault(row["disk_path"], []).append(row)

    keep_ids: set[int] = set()

    for disk_rows in groups.values():
        disk_rows.sort(key=lambda r: r["timestamp"])
        compacted = compact_rows(disk_rows, window_minutes)
        for row in compacted:
            keep_ids.add(row["id"])

    redundant = [row["id"] for row in rows if row["id"] not in keep_ids]
    logging.debug(
        "find_redundant_ids: %d total, %d keep, %d redundant",
        len(rows),
        len(keep_ids),
        len(redundant),
    )
    return redundant
