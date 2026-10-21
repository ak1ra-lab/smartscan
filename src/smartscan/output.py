"""Rich-powered terminal output: tables, JSON lines, and field formatting."""

from __future__ import annotations

import json
import sqlite3
import sys
from typing import Any, NamedTuple, cast

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from .fields import (
    ALL_HEALTH_FIELDS,
    CORE_FIELDS,
    EXTENDED_FIELDS,
    FieldDef,
    get_field,
    rotation_display,
)
from .models import SmartInfo

FIELD_WIDTH = 24

console = Console(highlight=False)


class FieldRow(NamedTuple):
    """One rendered table row, keyed by the underlying SMART field name."""

    key: str
    label: str
    value: str
    level: str | None


def _format_field_value(field: FieldDef, fields: SmartInfo) -> str:
    value = get_field(fields, field.key)
    if value is None or value == "N/A":
        return "N/A"
    if field.format_label:
        return field.format_label.format(value=value)
    if isinstance(value, (str, int, float)):
        return str(value)
    return "N/A"


def _format_fields(
    fields: SmartInfo,
    alerts_map: dict[str, str],
    verbose: bool = False,
) -> list[FieldRow]:
    """Build the rows to display.

    Default output shows core fields that the drive actually reports, plus any
    extended field that triggered an alert.  ``--verbose`` shows every field,
    including values the drive does not provide.
    """
    display_fields = list(CORE_FIELDS)
    if verbose:
        display_fields.extend(EXTENDED_FIELDS)
    else:
        display_fields.extend(f for f in EXTENDED_FIELDS if f.key in alerts_map)

    rows: list[FieldRow] = []
    for field in display_fields:
        value = _format_field_value(field, fields)
        level = alerts_map.get(field.key)
        if not verbose and value in ("", "N/A") and level is None:
            continue
        rows.append(FieldRow(field.key, field.label, value, level))

    return rows


def _alerts_map(alerts: list[Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for a in alerts:
        result[a.field] = a.level
    return result


def _print_fields(fields: SmartInfo, alerts: list[Any] | None = None, verbose: bool = False) -> None:
    alerts_list = alerts or []
    amap = _alerts_map(alerts_list)
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column(style="cyan", width=FIELD_WIDTH)
    table.add_column()
    for row in _format_fields(fields, amap, verbose=verbose):
        if row.level == "critical":
            style = "bold red"
            prefix = "!! "
        elif row.level == "warning":
            style = "yellow"
            prefix = "!  "
        else:
            style = None
            prefix = ""
        table.add_row(row.label, f"{prefix}{row.value}", style=style)
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


def print_lsblk_tree(devices: list[dict[str, object]]) -> None:
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


def print_lsblk_json(devices: list[dict[str, object]]) -> None:
    """Emit disk identifier trees as JSON lines to stdout."""
    for dev in devices:
        json.dump(dev, sys.stdout, ensure_ascii=False, default=str)
        sys.stdout.write("\n")
        sys.stdout.flush()


def _safe_default(field_def: FieldDef, col_val: Any) -> Any:
    if field_def.db_type == "REAL":
        return col_val
    if field_def.key == "user_capacity_bytes":
        return int(col_val) if col_val is not None else 0
    if col_val is None:
        return field_def.default
    if field_def.key == "rotation_rate":
        return col_val or "N/A"
    return col_val


def row_to_fields(row: sqlite3.Row) -> SmartInfo:
    """Convert a database row into the typed :class:`SmartInfo` dict, restoring display values."""
    row_keys = set(row.keys())
    fields = {
        field.key: _safe_default(field, row[field.db_column] if field.db_column in row_keys else None)
        for field in ALL_HEALTH_FIELDS
    }
    fields["rotation_rate_display"] = rotation_display(str(fields["rotation_rate"]))
    return cast(SmartInfo, fields)
