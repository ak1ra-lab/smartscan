"""Rich-powered terminal output: tables, JSON lines, and field formatting."""

from __future__ import annotations

import json
import sqlite3
import sys
from typing import Any

from rich.console import Console
from rich.table import Table

from .models import SmartInfo

FIELD_WIDTH = 24

console = Console(highlight=False)


def _format_fields(fields: SmartInfo) -> list[tuple[str, str, bool]]:
    uc_gib = fields["user_capacity_gib"]
    uc_display = f"{uc_gib} GiB" if uc_gib is not None else "N/A"

    realloc = fields["reallocated_sector_ct"]
    realloc_warn = False
    try:
        realloc_warn = int(realloc) > 0
    except (ValueError, TypeError):
        pass

    return [
        ("model_family", fields["model_family"], False),
        ("model_name", fields["model_name"], False),
        ("user_capacity", uc_display, False),
        ("rotation_rate", fields["rotation_rate_display"], False),
        ("interface_speed", fields["interface_speed"], False),
        ("power_on_time", f"{fields['power_on_time']} hours", False),
        ("power_cycle_count", fields["power_cycle_count"], False),
        ("temperature", f"{fields['temperature']}°C", False),
        ("reallocated_sector_ct", realloc, realloc_warn),
        ("ata_smart_error_log", fields["ata_smart_error_log"], False),
        ("self_test_status", fields["self_test_status"], False),
    ]


def _print_fields(fields: SmartInfo) -> None:
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style="cyan", width=FIELD_WIDTH)
    table.add_column()
    for label, value, is_warn in _format_fields(fields):
        style = "bold red" if is_warn else None
        table.add_row(label, value, style=style)
    console.print(table)


def print_table(disk_name: str, fields: SmartInfo) -> None:
    """Render the SMART fields for a single disk as a Rich-styled table."""
    console.rule(f"[bold]{disk_name}[/bold]")
    _print_fields(fields)
    console.print()


def print_query_table(
    disk_name: str, disk_path: str, timestamp: str, fields: SmartInfo
) -> None:
    """Render a historical query result row as a Rich-styled table with timestamp header."""
    console.rule(f"[bold]{timestamp} | {disk_name} ({disk_path})[/bold]")
    _print_fields(fields)
    console.print()


def print_json_output(
    disk_name: str,
    disk_path: str,
    fields: SmartInfo,
    raw_data: dict[str, Any] | None = None,
    timestamp: str | None = None,
) -> None:
    """Emit a single SMART record as a JSON line to stdout."""
    record: dict[str, Any] = {
        "disk_name": disk_name,
        "disk_path": disk_path,
        **fields,
    }
    if timestamp:
        record["timestamp"] = timestamp
    json.dump(record, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    sys.stdout.flush()


def row_to_fields(row: sqlite3.Row) -> SmartInfo:
    """Convert a database row into the typed :class:`SmartInfo` dict, restoring display values."""
    rr = row["rotation_rate"]
    rr_display = f"{rr} rpm" if rr not in ("N/A", "0") else "SSD (no rotation)"
    return SmartInfo(
        model_family=row["model_family"],
        model_name=row["model_name"],
        user_capacity_bytes=row["user_capacity_bytes"],
        user_capacity_gib=row["user_capacity_gib"],
        rotation_rate=rr,
        rotation_rate_display=rr_display,
        interface_speed=row["interface_speed"],
        power_on_time=row["power_on_time_hours"],
        power_cycle_count=row["power_cycle_count"],
        temperature=row["temperature_celsius"],
        reallocated_sector_ct=row["reallocated_sector_ct"],
        ata_smart_error_log=row["ata_smart_error_log_count"],
        self_test_status=row["self_test_status"],
    )
