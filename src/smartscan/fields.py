"""SMART field definitions — single source of truth for field metadata.

Each :class:`FieldDef` describes one field in :class:`~models.SmartInfo`,
including its database column name, display label, output grouping,
and prompt presentation details.

Field sections follow the display policy:

- ``core``: health signals that can change the verdict or require action.
  They are shown by default when the drive reports a value.
- ``extended``: diagnostic and context counters.  They are shown with
  ``--verbose``, or automatically when the field triggers an alert.
- ``identity``: internal columns that are not rendered directly.

Fields that a drive does not report are omitted from the default table
instead of being printed as ``N/A``.  This keeps the default view focused on
signals that are actually meaningful for the drive in question.
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


def rotation_display(rotation_rate: str) -> str:
    """Return a human-readable rotation rate string.

    ``"7200"`` → ``"7200 rpm"``, ``"0"`` → ``"SSD (no rotation)"``,
    unknown values → ``"N/A"``.
    """
    if not rotation_rate or rotation_rate == "N/A":
        return "N/A"
    if rotation_rate == "0":
        return "SSD (no rotation)"
    return f"{rotation_rate} rpm"


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
        key="endurance_used_percent",
        db_column="endurance_used_percent",
        label="endurance_used",
        db_type="TEXT",
        section="core",
        format_label="{value}%",
        prompt_label="Endurance Used",
        prompt_section="critical",
        is_time_series=True,
    ),
    FieldDef(
        key="available_spare_percent",
        db_column="available_spare_percent",
        label="available_spare",
        db_type="TEXT",
        section="core",
        format_label="{value}%",
        prompt_label="Available Spare",
        prompt_section="critical",
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
        key="pending_defects_count",
        db_column="pending_defects_count",
        label="pending_defects",
        db_type="TEXT",
        section="core",
        prompt_label="Pending Defects",
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
        key="sata_phy_icrc_errors",
        db_column="sata_phy_icrc_errors",
        label="sata_phy_icrc_errors",
        db_type="TEXT",
        section="extended",
        prompt_label="SATA PHY ICRC Errors",
        prompt_section="secondary",
    ),
    FieldDef(
        key="sata_phy_crc_errors",
        db_column="sata_phy_crc_errors",
        label="sata_phy_crc_errors",
        db_type="TEXT",
        section="extended",
        prompt_label="SATA PHY CRC Errors",
        prompt_section="secondary",
    ),
    FieldDef(
        key="sata_phy_comreset_count",
        db_column="sata_phy_comreset_count",
        label="sata_phy_comreset_count",
        db_type="TEXT",
        section="extended",
        prompt_label="SATA PHY COMRESET Count",
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
        key="data_written_tib",
        db_column="data_written_tib",
        label="data_written",
        db_type="REAL",
        section="extended",
        format_label="{value} TiB",
        prompt_label="Data Written",
        prompt_section="secondary",
        is_time_series=True,
    ),
    FieldDef(
        key="unsafe_shutdowns",
        db_column="unsafe_shutdowns",
        label="unsafe_shutdowns",
        db_type="TEXT",
        section="extended",
        prompt_label="Unsafe Shutdowns",
        prompt_section="secondary",
        is_time_series=True,
    ),
    FieldDef(
        key="scsi_uncorrected_errors",
        db_column="scsi_uncorrected_errors",
        label="scsi_uncorrected_errors",
        db_type="TEXT",
        section="core",
        prompt_label="SCSI Uncorrected Errors",
        prompt_section="critical",
    ),
    FieldDef(
        key="scsi_corrected_errors",
        db_column="scsi_corrected_errors",
        label="scsi_corrected_errors",
        db_type="TEXT",
        section="extended",
        prompt_label="SCSI Corrected Errors",
        prompt_section="secondary",
    ),
    FieldDef(
        key="scsi_sas_phy_errors",
        db_column="scsi_sas_phy_errors",
        label="scsi_sas_phy_errors",
        db_type="TEXT",
        section="extended",
        prompt_label="SAS PHY Errors",
        prompt_section="secondary",
    ),
    FieldDef(
        key="farm_unrecoverable_read_errors",
        db_column="farm_unrecoverable_read_errors",
        label="farm_unc_read",
        db_type="TEXT",
        section="core",
        prompt_label="FARM Unrecoverable Read Errors",
        prompt_section="critical",
    ),
    FieldDef(
        key="farm_unrecoverable_write_errors",
        db_column="farm_unrecoverable_write_errors",
        label="farm_unc_write",
        db_type="TEXT",
        section="core",
        prompt_label="FARM Unrecoverable Write Errors",
        prompt_section="critical",
    ),
    FieldDef(
        key="farm_read_recovery_attempts",
        db_column="farm_read_recovery_attempts",
        label="farm_read_recovery",
        db_type="TEXT",
        section="extended",
        prompt_label="FARM Read Recovery Attempts",
        prompt_section="secondary",
    ),
    FieldDef(
        key="farm_crc_errors",
        db_column="farm_crc_errors",
        label="farm_crc_errors",
        db_type="TEXT",
        section="extended",
        prompt_label="FARM CRC Errors",
        prompt_section="secondary",
    ),
    FieldDef(
        key="farm_head_flight_hours",
        db_column="farm_head_flight_hours",
        label="farm_head_hours",
        db_type="TEXT",
        section="extended",
        prompt_label="FARM Head Flight Hours",
        prompt_section="secondary",
        is_time_series=True,
    ),
    FieldDef(
        key="farm_head_load_events",
        db_column="farm_head_load_events",
        label="farm_head_loads",
        db_type="TEXT",
        section="extended",
        prompt_label="FARM Head Load Events",
        prompt_section="secondary",
        is_time_series=True,
    ),
    FieldDef(
        key="farm_reset_count",
        db_column="farm_reset_count",
        label="farm_reset_count",
        db_type="TEXT",
        section="extended",
        prompt_label="FARM Reset Count",
        prompt_section="secondary",
        is_time_series=True,
    ),
    FieldDef(
        key="farm_temperature_max",
        db_column="farm_temperature_max",
        label="farm_temp_max",
        db_type="TEXT",
        section="extended",
        format_label="{value}°C",
        prompt_label="FARM Max Temperature",
        prompt_section="secondary",
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
CRITICAL_PROMPT_FIELDS = tuple(f for f in _PROMPT_FIELDS if f.prompt_section == "critical")
SECONDARY_PROMPT_FIELDS = tuple(f for f in _PROMPT_FIELDS if f.prompt_section == "secondary")

TIME_SERIES_FIELDS: frozenset[str] = frozenset(f.key for f in _FIELDS if f.is_time_series)

MONITORED_FIELDS: frozenset[str] = frozenset(
    {
        "smart_status",
        "temperature",
        "endurance_used_percent",
        "available_spare_percent",
        "unsafe_shutdowns",
        "pending_defects_count",
        "sata_phy_icrc_errors",
        "sata_phy_crc_errors",
        "sata_phy_comreset_count",
        "scsi_uncorrected_errors",
        "scsi_corrected_errors",
        "scsi_sas_phy_errors",
        "farm_unrecoverable_read_errors",
        "farm_unrecoverable_write_errors",
        "farm_read_recovery_attempts",
        "farm_crc_errors",
        "farm_reset_count",
        "farm_temperature_max",
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
