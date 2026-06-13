"""Rich-powered terminal output: tables, JSON lines, and field formatting."""

from __future__ import annotations

import json
import sqlite3
import sys
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from .fields import CORE_FIELDS, EXTENDED_FIELDS, FieldDef, get_field
from .models import SmartInfo

FIELD_WIDTH = 24

console = Console(highlight=False)


def _format_field_value(field: FieldDef, fields: SmartInfo) -> str:
    value = get_field(fields, field.key)
    if field.key == "user_capacity_gib":
        return f"{value} GiB" if value is not None else "N/A"
    if field.format_label:
        return field.format_label.format(value=value)
    if isinstance(value, (str, int, float)):
        return str(value)
    return "N/A"


def _build_core_rows(fields: SmartInfo) -> list[tuple[str, str]]:
    return [(f.label, _format_field_value(f, fields)) for f in CORE_FIELDS]


def _build_extended_rows(fields: SmartInfo) -> list[tuple[str, str]]:
    return [(f.label, _format_field_value(f, fields)) for f in EXTENDED_FIELDS]


def _format_fields(
    fields: SmartInfo,
    alerts_map: dict[str, str],
    verbose: bool = False,
) -> list[tuple[str, str, str | None]]:
    rows: list[tuple[str, str, str | None]] = []

    for label, value in _build_core_rows(fields):
        style = alerts_map.get(label)
        rows.append((label, value, style))

    if verbose:
        for label, value in _build_extended_rows(fields):
            style = alerts_map.get(label)
            rows.append((label, value, style))

    return rows


def _alerts_map(alerts: list[Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for a in alerts:
        result[a.field] = a.level
    return result


def _print_fields(
    fields: SmartInfo, alerts: list[Any] | None = None, verbose: bool = False
) -> None:
    alerts_list = alerts or []
    amap = _alerts_map(alerts_list)
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style="cyan", width=FIELD_WIDTH)
    table.add_column()
    for label, value, style_name in _format_fields(fields, amap, verbose=verbose):
        if style_name == "critical":
            style = "bold red"
            prefix = "!! "
        elif style_name == "warning":
            style = "yellow"
            prefix = "!  "
        else:
            style = None
            prefix = ""
        table.add_row(label, f"{prefix}{value}", style=style)
    console.print(table)

    if alerts_list:
        summary_parts = []
        criticals = [a for a in alerts_list if a.level == "critical"]
        warnings = [a for a in alerts_list if a.level == "warning"]
        if criticals:
            summary_parts.append(f"[bold red]{len(criticals)} critical[/bold red]")
        if warnings:
            summary_parts.append(f"[yellow]{len(warnings)} warning[/yellow]")
        console.print("  " + ", ".join(summary_parts))
        console.print()


def print_table(
    disk_name: str,
    fields: SmartInfo,
    alerts: list[Any] | None = None,
    verbose: bool = False,
) -> None:
    """Render the SMART fields for a single disk as a Rich-styled table."""
    console.rule(f"[bold]{disk_name}[/bold]")
    _print_fields(fields, alerts, verbose=verbose)


def print_query_table(
    disk_name: str,
    disk_path: str,
    timestamp: str,
    fields: SmartInfo,
    alerts: list[Any] | None = None,
    verbose: bool = False,
) -> None:
    """Render a historical query result row as a Rich-styled table with timestamp header."""
    console.rule(f"[bold]{timestamp} | {disk_name} ({disk_path})[/bold]")
    _print_fields(fields, alerts, verbose=verbose)


def print_json_output(
    disk_name: str,
    disk_path: str,
    fields: SmartInfo,
    raw_data: dict[str, Any] | None = None,
    timestamp: str | None = None,
    llm_analysis: str | None = None,
) -> None:
    """Emit a single SMART record as a JSON line to stdout."""
    record: dict[str, Any] = {
        "disk_name": disk_name,
        "disk_path": disk_path,
        **fields,
    }
    if timestamp:
        record["timestamp"] = timestamp
    if llm_analysis:
        record["llm_analysis"] = llm_analysis
    json.dump(record, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    sys.stdout.flush()


def print_llm_analysis(text: str) -> None:
    """Display LLM analysis text in a styled panel."""
    panel = Panel(
        Text(text, style="italic"),
        title="LLM Analysis",
        border_style="dim blue",
        padding=(0, 1),
    )
    console.print(panel)
    console.print()


def print_identify_tree(devices: list[dict[str, object]]) -> None:
    """Render disk identifier trees as a Rich-styled tree."""
    for dev in devices:
        label = str(dev["device"])
        extras = []
        model = dev.get("model", "N/A")
        if model != "N/A":
            extras.append(str(model))
        size_human = dev.get("size_human", "N/A")
        if size_human != "N/A":
            extras.append(str(size_human))
        if extras:
            label += f"  [{', '.join(extras)}]"

        tree = Tree(label, guide_style="dim")
        sources = dev.get("sources", {})
        if isinstance(sources, dict):
            for source, paths in sources.items():
                if not isinstance(paths, list) or not paths:
                    continue
                branch = tree.add(f"[bold cyan]{source}[/bold cyan]")
                for p in paths:
                    branch.add(str(p))
        console.print(tree)
        console.print()


def print_identify_json(devices: list[dict[str, object]]) -> None:
    """Emit disk identifier trees as JSON lines to stdout."""
    for dev in devices:
        json.dump(dev, sys.stdout, ensure_ascii=False, default=str)
        sys.stdout.write("\n")
        sys.stdout.flush()


def row_to_fields(row: sqlite3.Row) -> SmartInfo:
    """Convert a database row into the typed :class:`SmartInfo` dict, restoring display values."""
    from .fields import ALL_HEALTH_FIELDS

    raw: dict[str, Any] = {}
    for f in ALL_HEALTH_FIELDS:
        col_val = row[f.db_column]
        if col_val is None and f.key == "user_capacity_gib":
            raw[f.key] = None
        elif col_val is None:
            raw[f.key] = f.default
        elif f.key == "rotation_rate":
            raw[f.key] = col_val or "N/A"
        else:
            raw[f.key] = col_val

    rr = raw.get("rotation_rate", "") or ""
    rr_display = f"{rr} rpm" if rr not in ("N/A", "0", "") else "SSD (no rotation)"

    return SmartInfo(
        model_family=raw.get("model_family", "N/A"),
        model_name=raw.get("model_name", "N/A"),
        serial_number=raw.get("serial_number", "N/A"),
        firmware_version=raw.get("firmware_version", "N/A"),
        user_capacity_bytes=raw.get("user_capacity_bytes", 0),
        user_capacity_gib=raw.get("user_capacity_gib"),
        rotation_rate=raw.get("rotation_rate", "N/A"),
        rotation_rate_display=rr_display,
        interface_speed=raw.get("interface_speed", "N/A"),
        power_on_time=raw.get("power_on_time", "N/A"),
        power_cycle_count=raw.get("power_cycle_count", "N/A"),
        smart_status=raw.get("smart_status", "N/A"),
        temperature=raw.get("temperature", "N/A"),
        reallocated_sector_ct=raw.get("reallocated_sector_ct", "0"),
        current_pending_sector=raw.get("current_pending_sector", "0"),
        offline_uncorrectable=raw.get("offline_uncorrectable", "0"),
        reallocated_event_count=raw.get("reallocated_event_count", "0"),
        ata_smart_error_log=raw.get("ata_smart_error_log", "0"),
        self_test_status=raw.get("self_test_status", "N/A"),
        udma_crc_error_count=raw.get("udma_crc_error_count", "0"),
        raw_read_error_rate=raw.get("raw_read_error_rate", "0"),
        spin_retry_count=raw.get("spin_retry_count", "0"),
        power_off_retract_count=raw.get("power_off_retract_count", "0"),
        load_cycle_count=raw.get("load_cycle_count", "0"),
        helium_level=raw.get("helium_level", "0"),
    )
