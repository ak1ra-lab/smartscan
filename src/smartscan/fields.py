"""SMART field definitions — single source of truth for field metadata.

Each :class:`FieldDef` describes one field in :class:`~models.SmartInfo`,
including its database column name, display label, output grouping,
and prompt presentation details.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .models import SmartInfo

Section = Literal["core", "extended", "identity"]
PromptSection = Literal["basic", "critical", "secondary"] | None


@dataclass(frozen=True)
class FieldDef:
    """Metadata for one SMART health/identity field."""

    key: str
    db_column: str
    label: str
    db_type: str
    section: Section
    default: str = "N/A"
    format_label: str | None = None
    prompt_label: str | None = None
    prompt_section: PromptSection = None
    is_time_series: bool = False


def get_field(fields: SmartInfo, key: str) -> Any:
    return fields[key]  # ty: ignore[invalid-key]


_FIELDS: tuple[FieldDef, ...] = (
    FieldDef(
        key="user_capacity_bytes",
        db_column="user_capacity_bytes",
        label="",
        db_type="INTEGER",
        section="identity",
        default="0",
    ),
    FieldDef(
        key="rotation_rate",
        db_column="rotation_rate",
        label="",
        db_type="TEXT",
        section="identity",
    ),
    FieldDef(
        key="model_family",
        db_column="model_family",
        label="model_family",
        db_type="TEXT",
        section="core",
        prompt_label="Model Family",
        prompt_section="basic",
    ),
    FieldDef(
        key="model_name",
        db_column="model_name",
        label="model_name",
        db_type="TEXT",
        section="core",
        prompt_label="Model Name",
        prompt_section="basic",
    ),
    FieldDef(
        key="serial_number",
        db_column="serial_number",
        label="serial_number",
        db_type="TEXT",
        section="extended",
    ),
    FieldDef(
        key="firmware_version",
        db_column="firmware_version",
        label="firmware_version",
        db_type="TEXT",
        section="extended",
    ),
    FieldDef(
        key="smart_status",
        db_column="smart_status",
        label="smart_status",
        db_type="TEXT",
        section="core",
        prompt_label="SMART Status",
        prompt_section="basic",
    ),
    FieldDef(
        key="user_capacity_gib",
        db_column="user_capacity_gib",
        label="user_capacity",
        db_type="REAL",
        section="core",
        format_label="{value} GiB",
        prompt_label="Capacity",
        prompt_section="basic",
    ),
    FieldDef(
        key="rotation_rate_display",
        db_column="",
        label="rotation_rate",
        db_type="",
        section="core",
        prompt_label="Rotation",
        prompt_section="basic",
    ),
    FieldDef(
        key="power_on_time",
        db_column="power_on_time_hours",
        label="power_on_time",
        db_type="TEXT",
        section="core",
        format_label="{value} hours",
        prompt_label="Power On Time",
        prompt_section="basic",
        is_time_series=True,
    ),
    FieldDef(
        key="temperature",
        db_column="temperature_celsius",
        label="temperature",
        db_type="TEXT",
        section="core",
        format_label="{value}°C",
        prompt_label="Temperature",
        prompt_section="basic",
    ),
    FieldDef(
        key="reallocated_sector_ct",
        db_column="reallocated_sector_ct",
        label="reallocated_sector_ct",
        db_type="TEXT",
        section="core",
        default="0",
        prompt_label="Reallocated Sectors",
        prompt_section="critical",
    ),
    FieldDef(
        key="current_pending_sector",
        db_column="current_pending_sector",
        label="current_pending_sector",
        db_type="TEXT",
        section="core",
        default="0",
        prompt_label="Current Pending Sectors",
        prompt_section="critical",
    ),
    FieldDef(
        key="offline_uncorrectable",
        db_column="offline_uncorrectable",
        label="offline_uncorrectable",
        db_type="TEXT",
        section="core",
        default="0",
        prompt_label="Offline Uncorrectable",
        prompt_section="critical",
    ),
    FieldDef(
        key="reallocated_event_count",
        db_column="reallocated_event_count",
        label="reallocated_event_count",
        db_type="TEXT",
        section="extended",
        default="0",
        prompt_label="Reallocated Event Count",
        prompt_section="critical",
    ),
    FieldDef(
        key="ata_smart_error_log",
        db_column="ata_smart_error_log_count",
        label="ata_smart_error_log",
        db_type="TEXT",
        section="core",
        default="0",
        prompt_label="ATA Error Log Count",
        prompt_section="critical",
    ),
    FieldDef(
        key="self_test_status",
        db_column="self_test_status",
        label="self_test_status",
        db_type="TEXT",
        section="core",
        prompt_label="Self-Test Status",
        prompt_section="critical",
    ),
    FieldDef(
        key="udma_crc_error_count",
        db_column="udma_crc_error_count",
        label="udma_crc_error_count",
        db_type="TEXT",
        section="extended",
        default="0",
        prompt_label="UDMA CRC Errors",
        prompt_section="secondary",
    ),
    FieldDef(
        key="raw_read_error_rate",
        db_column="raw_read_error_rate",
        label="raw_read_error_rate",
        db_type="TEXT",
        section="extended",
        default="0",
        prompt_label="Raw Read Error Rate",
        prompt_section="secondary",
    ),
    FieldDef(
        key="spin_retry_count",
        db_column="spin_retry_count",
        label="spin_retry_count",
        db_type="TEXT",
        section="extended",
        default="0",
        prompt_label="Spin Retry Count",
        prompt_section="secondary",
    ),
    FieldDef(
        key="power_off_retract_count",
        db_column="power_off_retract_count",
        label="power_off_retract_count",
        db_type="TEXT",
        section="extended",
        default="0",
        prompt_label="Power-Off Retract Count",
        prompt_section="secondary",
        is_time_series=True,
    ),
    FieldDef(
        key="load_cycle_count",
        db_column="load_cycle_count",
        label="load_cycle_count",
        db_type="TEXT",
        section="extended",
        default="0",
        prompt_label="Load Cycle Count",
        prompt_section="secondary",
        is_time_series=True,
    ),
    FieldDef(
        key="helium_level",
        db_column="helium_level",
        label="helium_level",
        db_type="TEXT",
        section="extended",
        default="0",
        prompt_label="Helium Level",
        prompt_section="secondary",
    ),
    FieldDef(
        key="power_cycle_count",
        db_column="power_cycle_count",
        label="power_cycle_count",
        db_type="TEXT",
        section="extended",
        prompt_label="Power Cycles",
        prompt_section="basic",
        is_time_series=True,
    ),
    FieldDef(
        key="interface_speed",
        db_column="interface_speed",
        label="interface_speed",
        db_type="TEXT",
        section="extended",
    ),
)


CORE_FIELDS = tuple(f for f in _FIELDS if f.section == "core")
EXTENDED_FIELDS = tuple(f for f in _FIELDS if f.section == "extended")
ALL_HEALTH_FIELDS = tuple(f for f in _FIELDS if f.db_column)

_PROMPT_FIELDS = tuple(f for f in _FIELDS if f.prompt_section is not None)

BASIC_PROMPT_FIELDS = tuple(f for f in _PROMPT_FIELDS if f.prompt_section == "basic")
CRITICAL_PROMPT_FIELDS = tuple(
    f for f in _PROMPT_FIELDS if f.prompt_section == "critical"
)
SECONDARY_PROMPT_FIELDS = tuple(
    f for f in _PROMPT_FIELDS if f.prompt_section == "secondary"
)

TIME_SERIES_FIELDS: frozenset[str] = frozenset(
    f.key for f in _FIELDS if f.is_time_series
)

MONITORED_FIELDS: frozenset[str] = frozenset(
    {
        "smart_status",
        "temperature",
        "reallocated_sector_ct",
        "current_pending_sector",
        "offline_uncorrectable",
        "reallocated_event_count",
        "ata_smart_error_log",
        "self_test_status",
        "udma_crc_error_count",
        "raw_read_error_rate",
        "spin_retry_count",
        "helium_level",
    }
)


def db_columns() -> tuple[str, ...]:
    """Return the database column names for all persisted health fields."""
    return tuple(f.db_column for f in ALL_HEALTH_FIELDS)
