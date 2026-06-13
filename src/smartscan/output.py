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

from .models import SmartInfo

FIELD_WIDTH = 24

console = Console(highlight=False)


def _build_core_rows(fields: SmartInfo) -> list[tuple[str, str]]:
    gib = fields["user_capacity_gib"]
    return [
        ("model_family", fields["model_family"]),
        ("model_name", fields["model_name"]),
        ("smart_status", fields["smart_status"]),
        ("user_capacity", f"{gib} GiB" if gib is not None else "N/A"),
        ("rotation_rate", fields["rotation_rate_display"]),
        ("power_on_time", f"{fields['power_on_time']} hours"),
        ("temperature", f"{fields['temperature']}°C"),
        ("reallocated_sector_ct", fields["reallocated_sector_ct"]),
        ("current_pending_sector", fields["current_pending_sector"]),
        ("offline_uncorrectable", fields["offline_uncorrectable"]),
        ("ata_smart_error_log", fields["ata_smart_error_log"]),
        ("self_test_status", fields["self_test_status"]),
    ]


def _build_extended_rows(fields: SmartInfo) -> list[tuple[str, str]]:
    return [
        ("serial_number", fields["serial_number"]),
        ("firmware_version", fields["firmware_version"]),
        ("interface_speed", fields["interface_speed"]),
        ("power_cycle_count", fields["power_cycle_count"]),
        ("reallocated_event_count", fields["reallocated_event_count"]),
        ("udma_crc_error_count", fields["udma_crc_error_count"]),
        ("raw_read_error_rate", fields["raw_read_error_rate"]),
        ("spin_retry_count", fields["spin_retry_count"]),
        ("power_off_retract_count", fields["power_off_retract_count"]),
        ("load_cycle_count", fields["load_cycle_count"]),
        ("helium_level", fields["helium_level"]),
    ]


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
    rr = row["rotation_rate"] or ""
    rr_display = f"{rr} rpm" if rr not in ("N/A", "0", "") else "SSD (no rotation)"
    return SmartInfo(
        model_family=row["model_family"] or "N/A",
        model_name=row["model_name"] or "N/A",
        serial_number=row["serial_number"] or "N/A",
        firmware_version=row["firmware_version"] or "N/A",
        user_capacity_bytes=row["user_capacity_bytes"] or 0,
        user_capacity_gib=row["user_capacity_gib"],
        rotation_rate=rr or "N/A",
        rotation_rate_display=rr_display,
        interface_speed=row["interface_speed"] or "N/A",
        power_on_time=row["power_on_time_hours"] or "N/A",
        power_cycle_count=row["power_cycle_count"] or "N/A",
        smart_status=row["smart_status"] or "N/A",
        temperature=row["temperature_celsius"] or "N/A",
        reallocated_sector_ct=row["reallocated_sector_ct"] or "0",
        current_pending_sector=row["current_pending_sector"] or "0",
        offline_uncorrectable=row["offline_uncorrectable"] or "0",
        reallocated_event_count=row["reallocated_event_count"] or "0",
        ata_smart_error_log=row["ata_smart_error_log_count"] or "0",
        self_test_status=row["self_test_status"] or "N/A",
        udma_crc_error_count=row["udma_crc_error_count"] or "0",
        raw_read_error_rate=row["raw_read_error_rate"] or "0",
        spin_retry_count=row["spin_retry_count"] or "0",
        power_off_retract_count=row["power_off_retract_count"] or "0",
        load_cycle_count=row["load_cycle_count"] or "0",
        helium_level=row["helium_level"] or "0",
    )
