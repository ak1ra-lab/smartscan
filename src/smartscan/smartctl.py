"""Interact with smartctl: disk discovery, SMART data collection, field extraction."""

from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Any

from .constants import SMARTCTL_ERROR_MSGS
from .exceptions import DiskNotFoundError, SmartctlError
from .models import SmartInfo


def safe_get(data: dict[str, Any] | Any, *keys: str, default: Any = "N/A") -> Any:
    """Safely traverse nested dicts returning a default for missing or empty values."""
    for key in keys:
        if isinstance(data, dict):
            data = data.get(key)
        else:
            return default
    if data is None or data == "" or data == "null":
        return default
    return data


def find_in_table(
    data: dict[str, Any],
    table_keys: tuple[str, ...],
    where_key: str,
    where_value: str,
    extract_keys: tuple[str, ...],
    default: str = "0",
) -> str:
    """Look up a value in a nested SMART attribute table by matching a row condition."""
    table = data
    for key in table_keys:
        if isinstance(table, dict):
            table = table.get(key, [])
        else:
            return default
    if not isinstance(table, list):
        return default
    for entry in table:
        if not isinstance(entry, dict):
            continue
        if entry.get(where_key) != where_value:
            continue
        value = entry
        for key in extract_keys:
            if isinstance(value, dict):
                value = value.get(key, default)
            else:
                return default
        if value is None or value == "":
            return default
        return str(value)
    return default


def check_smartctl_error(returncode: int | None) -> None:
    """Log human-readable error messages for each bit in the smartctl exit code."""
    if returncode is None or returncode == 0:
        return
    logging.error("smartctl returned error code: %d", returncode)
    for i in range(8):
        if (returncode >> i) & 1:
            logging.error("  %s", SMARTCTL_ERROR_MSGS[i])


def find_disks(pattern: str) -> list[Path]:
    """Discover ATA and NVMe disk devices under ``/dev/disk/by-id/`` matching a regex pattern.

    Multiple by-id entries may point to the same physical block device
    (e.g. ``nvme-eui.*`` and ``nvme-Model_Serial`` both resolve to the same
    ``nvme0n1``).  Vendor model names are preferred over EUI-based hex
    identifiers, and names without a namespace suffix (``_1``) are preferred
    over those with one.  Only one entry per physical disk is returned.

    Raises:
        DiskNotFoundError: If no matching disks are found or the by-id directory is missing.
    """
    logging.info("Searching for disk devices matching pattern: %s", pattern)
    by_id = Path("/dev/disk/by-id")
    if not by_id.is_dir():
        raise DiskNotFoundError(f"Directory not found: {by_id}")

    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        raise DiskNotFoundError(f"Invalid regex pattern: {exc}") from exc

    disks: list[Path] = []
    by_target: dict[Path, Path] = {}
    _ns_re = re.compile(r"_\d+$")
    for entry in sorted(by_id.iterdir()):
        if not entry.is_symlink():
            continue
        name = entry.name
        if not name.startswith(("ata-", "nvme-")):
            continue
        if re.search(r"-part\d+$", name):
            continue
        if not compiled.search(name):
            continue
        target = entry.resolve()
        if target in by_target:
            existing_name = by_target[target].name
            old_is_eui = existing_name.startswith("nvme-eui.")
            new_is_eui = name.startswith("nvme-eui.")
            if old_is_eui and not new_is_eui:
                by_target[target] = entry
            elif not old_is_eui and not new_is_eui:
                old_ns = bool(_ns_re.search(existing_name))
                new_ns = bool(_ns_re.search(name))
                if old_ns and not new_ns:
                    by_target[target] = entry
        else:
            by_target[target] = entry
    disks = sorted(by_target.values(), key=lambda p: p.name)

    if not disks:
        raise DiskNotFoundError(f"No disk devices found matching pattern: {pattern}")

    logging.info("Found %d disk(s):", len(disks))
    for d in disks:
        logging.debug("  %s", d)

    return disks


def run_smartctl(disk_path: Path) -> tuple[dict[str, Any], int]:
    """Run ``smartctl --all --json`` against a disk and return parsed JSON and exit code.

    Raises:
        SmartctlError: If the smartctl binary is not found.
    """
    try:
        result = subprocess.run(
            ["smartctl", "--all", "--json", str(disk_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        raise SmartctlError(
            "smartctl not found. Please install smartmontools."
        ) from None
    except subprocess.TimeoutExpired:
        logging.error("smartctl timed out for %s", disk_path)
        return {}, -1

    check_smartctl_error(result.returncode)

    try:
        data = json.loads(result.stdout) if result.stdout.strip() else {}
    except json.JSONDecodeError:
        logging.error("Failed to parse smartctl JSON output for %s", disk_path)
        data = {}

    return data, result.returncode


_ATA_ATTRIBUTES = (
    "ata_smart_attributes",
    "table",
)


def _find_attr(data: dict[str, Any], name: str) -> str:
    return find_in_table(data, _ATA_ATTRIBUTES, "name", name, ("raw", "string"))


def _extract_nvme_health(data: dict[str, Any]) -> dict[str, str]:
    log = data.get("nvme_smart_health_information_log", {})

    smart_passed = safe_get(data, "smart_status", "passed", default=False)
    smart_status = "PASSED" if smart_passed is True else "FAILED"

    return {
        "power_on_time": str(safe_get(log, "power_on_hours", default="N/A")),
        "power_cycle_count": str(safe_get(log, "power_cycles", default="N/A")),
        "temperature": str(safe_get(log, "temperature", default="N/A")),
        "smart_status": smart_status,
        "error_log": str(safe_get(log, "num_err_log_entries", default="0")),
        "self_test": str(safe_get(log, "self_test", "status", "string")),
        "realloc": str(safe_get(log, "media_errors", default="N/A")),
        "current_pending": "N/A",
        "offline_uncorrectable": "N/A",
        "reallocated_event": "N/A",
        "udma_crc": "N/A",
        "raw_read": "N/A",
        "spin_retry": "N/A",
        "power_off_retract": "N/A",
        "load_cycle": "N/A",
        "helium": "N/A",
    }


def _extract_ata_health(data: dict[str, Any]) -> dict[str, str]:
    smart_passed = safe_get(data, "smart_status", "passed", default=False)
    smart_status = "PASSED" if smart_passed is True else "FAILED"

    return {
        "power_on_time": str(safe_get(data, "power_on_time", "hours")),
        "power_cycle_count": str(safe_get(data, "power_cycle_count")),
        "temperature": str(safe_get(data, "temperature", "current")),
        "smart_status": smart_status,
        "error_log": str(
            safe_get(data, "ata_smart_error_log", "summary", "count", default="0")
        ),
        "self_test": str(
            safe_get(data, "ata_smart_data", "self_test", "status", "string")
        ),
        "realloc": _find_attr(data, "Reallocated_Sector_Ct"),
        "current_pending": _find_attr(data, "Current_Pending_Sector"),
        "offline_uncorrectable": _find_attr(data, "Offline_Uncorrectable"),
        "reallocated_event": _find_attr(data, "Reallocated_Event_Count"),
        "udma_crc": _find_attr(data, "UDMA_CRC_Error_Count"),
        "raw_read": _find_attr(data, "Raw_Read_Error_Rate"),
        "spin_retry": _find_attr(data, "Spin_Retry_Count"),
        "power_off_retract": _find_attr(data, "Power-Off_Retract_Count"),
        "load_cycle": _find_attr(data, "Load_Cycle_Count"),
        "helium": _find_attr(data, "Helium_Level"),
    }


def extract_fields(data: dict[str, Any]) -> SmartInfo:
    """Extract key SMART health metrics from raw smartctl JSON output into a typed dict."""
    model_family = str(safe_get(data, "model_family"))
    model_name = str(safe_get(data, "model_name"))
    serial_number = str(safe_get(data, "serial_number"))
    firmware_version = str(safe_get(data, "firmware_version"))

    uc_bytes = safe_get(data, "user_capacity", "bytes", default=0)
    try:
        uc_bytes = int(uc_bytes)
    except (ValueError, TypeError):
        uc_bytes = 0
    uc_gib = round(uc_bytes / (2**30), 2) if uc_bytes > 0 else None

    rotation_rate = str(safe_get(data, "rotation_rate"))
    rr_display = (
        f"{rotation_rate} rpm"
        if rotation_rate not in ("N/A", "0")
        else "SSD (no rotation)"
    )

    interface_speed = str(safe_get(data, "interface_speed", "current", "string"))

    if "nvme_smart_health_information_log" in data:
        h = _extract_nvme_health(data)
    else:
        h = _extract_ata_health(data)

    return SmartInfo(
        model_family=model_family,
        model_name=model_name,
        serial_number=serial_number,
        firmware_version=firmware_version,
        user_capacity_bytes=uc_bytes,
        user_capacity_gib=uc_gib,
        rotation_rate=rotation_rate,
        rotation_rate_display=rr_display,
        interface_speed=interface_speed,
        power_on_time=h["power_on_time"],
        power_cycle_count=h["power_cycle_count"],
        smart_status=h["smart_status"],
        temperature=h["temperature"],
        reallocated_sector_ct=h["realloc"],
        current_pending_sector=h["current_pending"],
        offline_uncorrectable=h["offline_uncorrectable"],
        reallocated_event_count=h["reallocated_event"],
        ata_smart_error_log=h["error_log"],
        self_test_status=h["self_test"],
        udma_crc_error_count=h["udma_crc"],
        raw_read_error_rate=h["raw_read"],
        spin_retry_count=h["spin_retry"],
        power_off_retract_count=h["power_off_retract"],
        load_cycle_count=h["load_cycle"],
        helium_level=h["helium"],
    )
