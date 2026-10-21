"""Shared test fixtures and helpers."""

from __future__ import annotations

from smartscan.models import SmartInfo


def make_fields(**overrides: str | int | float | None) -> SmartInfo:
    defaults: SmartInfo = {
        "model_family": "",
        "model_name": "",
        "serial_number": "N/A",
        "firmware_version": "N/A",
        "user_capacity_bytes": 0,
        "user_capacity_gib": None,
        "rotation_rate": "N/A",
        "rotation_rate_display": "SSD (no rotation)",
        "interface_speed": "N/A",
        "power_on_time": "N/A",
        "power_cycle_count": "N/A",
        "smart_status": "PASSED",
        "temperature": "N/A",
        "endurance_used_percent": "N/A",
        "available_spare_percent": "N/A",
        "data_written_tib": None,
        "unsafe_shutdowns": "N/A",
        "pending_defects_count": "N/A",
        "sata_phy_icrc_errors": "N/A",
        "sata_phy_crc_errors": "N/A",
        "sata_phy_comreset_count": "N/A",
        "scsi_uncorrected_errors": "N/A",
        "scsi_corrected_errors": "N/A",
        "scsi_sas_phy_errors": "N/A",
        "reallocated_sector_ct": "0",
        "current_pending_sector": "0",
        "offline_uncorrectable": "0",
        "reallocated_event_count": "0",
        "ata_smart_error_log": "0",
        "self_test_status": "N/A",
        "udma_crc_error_count": "0",
        "raw_read_error_rate": "0",
        "spin_retry_count": "0",
        "power_off_retract_count": "0",
        "load_cycle_count": "0",
        "helium_level": "0",
    }
    defaults.update(overrides)  # type: ignore[arg-type]
    return defaults
