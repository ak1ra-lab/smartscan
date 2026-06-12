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
    """Discover ATA disk devices under ``/dev/disk/by-id/`` matching a regex pattern.

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

    disks = []
    for entry in sorted(by_id.iterdir()):
        if not entry.is_symlink():
            continue
        name = entry.name
        if not name.startswith("ata-"):
            continue
        if re.search(r"-part\d+$", name):
            continue
        if not compiled.search(name):
            continue
        disks.append(entry)

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


def extract_fields(data: dict[str, Any]) -> SmartInfo:
    """Extract key SMART health metrics from raw smartctl JSON output into a typed dict."""
    model_family = str(safe_get(data, "model_family"))
    model_name = str(safe_get(data, "model_name"))

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

    power_on_time = str(safe_get(data, "power_on_time", "hours"))
    power_cycle_count = str(safe_get(data, "power_cycle_count"))
    temperature = str(safe_get(data, "temperature", "current"))

    realloc = find_in_table(
        data,
        ("ata_smart_attributes", "table"),
        "name",
        "Reallocated_Sector_Ct",
        ("raw", "string"),
    )

    error_log = str(
        safe_get(data, "ata_smart_error_log", "summary", "count", default="0")
    )
    self_test = str(safe_get(data, "ata_smart_data", "self_test", "status", "string"))

    return SmartInfo(
        model_family=model_family,
        model_name=model_name,
        user_capacity_bytes=uc_bytes,
        user_capacity_gib=uc_gib,
        rotation_rate=rotation_rate,
        rotation_rate_display=rr_display,
        interface_speed=interface_speed,
        power_on_time=power_on_time,
        power_cycle_count=power_cycle_count,
        temperature=temperature,
        reallocated_sector_ct=realloc,
        ata_smart_error_log=error_log,
        self_test_status=self_test,
    )
