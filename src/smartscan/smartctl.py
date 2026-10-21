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
from .fields import rotation_display
from .models import SmartInfo
from .utils import (
    compile_exclude_patterns,
    get_disk_info,
    is_excluded,
    is_whole_disk,
    safe_get,
)

SOURCE_DIRS = ("by-id", "by-path", "by-diskseq")

_SYSFS_NVME = Path("/sys/class/nvme")
_NVME_NAMESPACE_RE = re.compile(r"(nvme\d+)(?:c\d+)?n\d+")
_SCSI_LINK_RATE_RE = re.compile(r"(\d+(?:\.\d+)?\s*(?:Gbps|Gbit/s))")


def _compile_excludes(patterns: list[str] | None) -> list[re.Pattern[str]]:
    try:
        return compile_exclude_patterns(patterns)
    except ValueError as exc:
        raise DiskNotFoundError(str(exc)) from exc


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


def smartctl_error_lines(returncode: int) -> list[str]:
    """Return human-readable error descriptions for each bit in the smartctl exit code."""
    lines = [f"smartctl exit code: {returncode}"]
    if returncode < 0:
        lines.append(f"  Process terminated by signal {-returncode}")
        return lines
    for i in range(8):
        if (returncode >> i) & 1:
            lines.append(f"  {SMARTCTL_ERROR_MSGS[i]}")
    return lines


def check_smartctl_error(returncode: int | None) -> None:
    """Log human-readable error messages for each bit in the smartctl exit code."""
    if returncode is None or returncode <= 0:
        return
    for line in smartctl_error_lines(returncode):
        logging.error("  %s", line)


def find_disks(pattern: str, exclude_patterns: list[str] | None = None) -> list[Path]:
    """Discover ATA, NVMe, and SCSI disk devices under ``/dev/disk/by-id/`` matching a regex pattern.

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

    exclude_compiled = _compile_excludes(exclude_patterns)

    disks: list[Path] = []
    by_target: dict[Path, Path] = {}
    _ns_re = re.compile(r"_\d+$")
    for entry in sorted(by_id.iterdir()):
        if not entry.is_symlink():
            continue
        name = entry.name
        if not name.startswith(("ata-", "nvme-", "scsi-")):
            continue
        if re.search(r"-part\d+$", name):
            continue
        if not compiled.search(name):
            continue
        target = entry.resolve()
        if name.startswith("scsi-") and (not target.is_block_device() or target.name.startswith(("sr", "st"))):
            continue
        if exclude_compiled and is_excluded(name, str(target), exclude_compiled):
            continue
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


def _read_nvme_link_speed(disk_path: Path) -> str | None:
    """Return the current PCIe link speed and width for an NVMe namespace, if available."""
    try:
        name = disk_path.resolve().name
    except (OSError, RuntimeError):
        return None

    match = _NVME_NAMESPACE_RE.fullmatch(name)
    if match is None:
        return None

    device = _SYSFS_NVME / match.group(1) / "device"
    try:
        speed = (device / "current_link_speed").read_text(encoding="utf-8").strip()
        width = (device / "current_link_width").read_text(encoding="utf-8").strip()
    except OSError:
        return None

    if not speed or not width:
        return None
    return f"{speed} x{width}"


def _add_nvme_link_speed(data: dict[str, Any], disk_path: Path) -> None:
    """Add NVMe PCIe link speed to raw smartctl data when smartctl omitted it."""
    if "nvme_smart_health_information_log" not in data:
        return
    speed = _read_nvme_link_speed(disk_path)
    if speed is not None:
        data.setdefault("interface_speed", {"current": {"string": speed}})


def _add_seagate_farm_log(data: dict[str, Any], disk_path: Path) -> None:
    """Fetch the Seagate FARM log when the initial SMART scan reports support."""
    farm = data.get("seagate_farm_log")
    if not isinstance(farm, dict) or farm.get("supported") is not True:
        return
    if "page_1_drive_information" in farm or "drive_information" in farm:
        return

    farm_data, _ = _run_smartctl_json(disk_path, ("-l", "farm"))
    farm_log = farm_data.get("seagate_farm_log")
    if isinstance(farm_log, dict) and farm_log.get("supported") is True:
        data["seagate_farm_log"] = farm_log


def _run_smartctl_json(disk_path: Path, options: tuple[str, ...]) -> tuple[dict[str, Any], int]:
    """Run smartctl with the given options and return parsed JSON and exit code."""
    logging.debug("Running smartctl %s on %s", " ".join(options), disk_path)
    try:
        result = subprocess.run(
            ["smartctl", *options, "--json", str(disk_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        raise SmartctlError("smartctl not found. Please install smartmontools.") from None
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


def _needs_sat_fallback(data: dict[str, Any]) -> bool:
    """Return True when smartctl saw SCSI but produced no usable disk SMART data."""
    if safe_get(data, "device", "protocol", default=None) != "SCSI":
        return False
    return not any(key in data for key in ("ata_smart_attributes", "scsi_error_counter_log", "scsi_grown_defect_list"))


def _has_ata_data(data: dict[str, Any]) -> bool:
    return "ata_smart_attributes" in data or safe_get(data, "device", "protocol", default=None) == "ATA"


def run_smartctl(disk_path: Path) -> tuple[dict[str, Any], int]:
    """Run ``smartctl --xall --json`` against a disk and return parsed JSON and exit code.

    ``--xall`` is a superset of ``--all`` for ATA disks and identical to
    ``--all`` for NVMe disks.  SATA disks behind a SCSI/SAS HBA are retried
    with ``-d sat`` when auto-detection yields no usable SMART data.  Seagate
    drives additionally receive a FARM log read when the initial scan reports
    support.

    Raises:
        SmartctlError: If the smartctl binary is not found.
    """
    data, returncode = _run_smartctl_json(disk_path, ("--xall",))

    if _needs_sat_fallback(data):
        logging.debug("Retrying %s with -d sat", disk_path)
        sat_data, sat_returncode = _run_smartctl_json(disk_path, ("--xall", "-d", "sat"))
        if _has_ata_data(sat_data):
            data, returncode = sat_data, sat_returncode

    _add_seagate_farm_log(data, disk_path)
    _add_nvme_link_speed(data, disk_path)
    return data, returncode


_ATA_ATTRIBUTES = (
    "ata_smart_attributes",
    "table",
)


def _find_attr(data: dict[str, Any], name: str) -> str:
    return find_in_table(data, _ATA_ATTRIBUTES, "name", name, ("raw", "string"))


def _ata_error_log_count(data: dict[str, Any]) -> str:
    """Return the ATA error count, preferring the extended log over the summary log."""
    for section in ("extended", "summary"):
        count = safe_get(data, "ata_smart_error_log", section, "count", default=None)
        if count is not None:
            return str(count)
    return "0"


_NVME_DATA_UNIT_BYTES = 1000 * 512
_TIB_BYTES = 2**40

_SATA_PHY_ICRC_ERROR = 0x001
_SATA_PHY_COMRESET = 0x00A
_SATA_PHY_CRC_ERROR = 0x00B


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _nvme_data_units_to_tib(value: Any) -> float | None:
    units = _int_or_none(value)
    if units is None:
        return None
    return round(units * _NVME_DATA_UNIT_BYTES / _TIB_BYTES, 2)


def _devstat_value(data: dict[str, Any], name: str) -> int | None:
    pages = safe_get(data, "ata_device_statistics", "pages", default=None)
    if not isinstance(pages, list):
        return None
    for page in pages:
        if not isinstance(page, dict):
            continue
        table = page.get("table")
        if not isinstance(table, list):
            continue
        for entry in table:
            if isinstance(entry, dict) and entry.get("name") == name:
                return _int_or_none(entry.get("value"))
    return None


def _pending_defects_count(data: dict[str, Any]) -> str:
    count = safe_get(data, "ata_pending_defects_log", "count", default=None)
    return str(count) if count is not None else "N/A"


def _sata_phy_counter(data: dict[str, Any], counter_id: int) -> str:
    table = safe_get(data, "sata_phy_event_counters", "table", default=None)
    if not isinstance(table, list):
        return "N/A"
    for entry in table:
        if isinstance(entry, dict) and _int_or_none(entry.get("id")) == counter_id:
            value = _int_or_none(entry.get("value"))
            if value is not None:
                return str(value)
    return "N/A"


_SCSI_ERROR_KINDS = ("read", "write", "verify")


def _scsi_error_sum(data: dict[str, Any], key: str) -> str:
    total = 0
    found = False
    for kind in _SCSI_ERROR_KINDS:
        value = _int_or_none(safe_get(data, "scsi_error_counter_log", kind, key, default=None))
        if value is not None:
            total += value
            found = True
    return str(total) if found else "N/A"


def _scsi_sas_phy_errors(data: dict[str, Any]) -> str:
    total = 0
    found = False
    counters = (
        "Invalid DWORD count",
        "Running disparity error count",
        "Loss of DWORD synchronization count",
        "Phy reset problem count",
    )
    for port_key, port in data.items():
        if not port_key.startswith("scsi_sas_port_") or not isinstance(port, dict):
            continue
        for phy_key, phy in port.items():
            if not phy_key.startswith("phy_") or not isinstance(phy, dict):
                continue
            for counter in counters:
                value = _int_or_none(phy.get(counter))
                if value is not None:
                    total += value
                    found = True
    return str(total) if found else "N/A"


def _scsi_link_rate(data: dict[str, Any]) -> str:
    for port_key in sorted(key for key in data if key.startswith("scsi_sas_port_")):
        port = data[port_key]
        if not isinstance(port, dict):
            continue
        for phy_key in sorted(key for key in port if key.startswith("phy_")):
            phy = port[phy_key]
            if not isinstance(phy, dict):
                continue
            rate = phy.get("negotiated logical link rate")
            if isinstance(rate, str) and rate:
                match = _SCSI_LINK_RATE_RE.search(rate)
                return match.group(1) if match else rate
    return "N/A"


def _scsi_self_test_status(data: dict[str, Any]) -> str:
    entry = data.get("scsi_self_test_0")
    if not isinstance(entry, dict):
        return "N/A"
    if entry.get("self_test_in_progress"):
        return "Self-test in progress"
    result = safe_get(entry, "result", "string", default=None)
    return str(result) if result is not None else "N/A"


def _scsi_data_written_tib(data: dict[str, Any]) -> float | None:
    value = safe_get(data, "scsi_error_counter_log", "write", "gigabytes_processed", default=None)
    try:
        gigabytes = float(value)
    except (TypeError, ValueError):
        return None
    return round(gigabytes * 1_000_000_000 / _TIB_BYTES, 2)


def _farm_value(data: dict[str, Any], *paths: tuple[str, ...]) -> str:
    for path in paths:
        value = safe_get(data, "seagate_farm_log", *path, default=None)
        if value is not None:
            return str(value)
    return "N/A"


def _ata_endurance_used(data: dict[str, Any]) -> str:
    current = safe_get(data, "endurance_used", "current_percent", default=None)
    if current is not None:
        return str(current)
    value = _devstat_value(data, "Percentage Used Endurance Indicator")
    return str(value) if value is not None else "N/A"


def _ata_data_written_tib(data: dict[str, Any]) -> float | None:
    sectors = _devstat_value(data, "Logical Sectors Written")
    block_size = _int_or_none(safe_get(data, "logical_block_size", default=None))
    if sectors is None or block_size is None:
        return None
    return round(sectors * block_size / _TIB_BYTES, 2)


def _nvme_self_test_status(data: dict[str, Any]) -> str:
    current = safe_get(
        data,
        "nvme_self_test_log",
        "current_self_test_operation",
        "string",
        default=None,
    )
    if isinstance(current, str) and "in progress" in current.lower() and "no self-test" not in current.lower():
        return current

    table = safe_get(data, "nvme_self_test_log", "table", default=None)
    if isinstance(table, dict):
        latest = next(iter(table.values()), None)
    elif isinstance(table, list):
        latest = table[0] if table else None
    else:
        latest = None

    if latest is not None:
        result = safe_get(latest, "self_test_result", "string", default=None)
        if result is not None:
            return str(result)

    return str(current) if current is not None else "N/A"


def _extract_nvme_health(data: dict[str, Any]) -> SmartInfo:
    log = data.get("nvme_smart_health_information_log", {})

    smart_passed = safe_get(data, "smart_status", "passed", default=False)
    smart_status = "PASSED" if smart_passed is True else "FAILED"

    return SmartInfo(
        model_family=str(safe_get(data, "model_family")),
        model_name=str(safe_get(data, "model_name")),
        serial_number=str(safe_get(data, "serial_number")),
        firmware_version=str(safe_get(data, "firmware_version")),
        user_capacity_bytes=_parse_capacity_bytes(data),
        user_capacity_gib=_parse_capacity_gib(data),
        rotation_rate=str(safe_get(data, "rotation_rate")),
        rotation_rate_display=rotation_display(str(safe_get(data, "rotation_rate"))),
        interface_speed=str(safe_get(data, "interface_speed", "current", "string")),
        power_on_time=str(safe_get(log, "power_on_hours", default="N/A")),
        power_cycle_count=str(safe_get(log, "power_cycles", default="N/A")),
        smart_status=smart_status,
        temperature=str(safe_get(log, "temperature", default="N/A")),
        endurance_used_percent=str(safe_get(log, "percentage_used", default="N/A")),
        available_spare_percent=str(safe_get(log, "available_spare", default="N/A")),
        data_written_tib=_nvme_data_units_to_tib(safe_get(log, "data_units_written", default=None)),
        unsafe_shutdowns=str(safe_get(log, "unsafe_shutdowns", default="N/A")),
        pending_defects_count="N/A",
        sata_phy_icrc_errors="N/A",
        sata_phy_crc_errors="N/A",
        sata_phy_comreset_count="N/A",
        scsi_uncorrected_errors="N/A",
        scsi_corrected_errors="N/A",
        scsi_sas_phy_errors="N/A",
        farm_unrecoverable_read_errors="N/A",
        farm_unrecoverable_write_errors="N/A",
        farm_read_recovery_attempts="N/A",
        farm_crc_errors="N/A",
        farm_head_flight_hours="N/A",
        farm_head_load_events="N/A",
        farm_reset_count="N/A",
        farm_temperature_max="N/A",
        reallocated_sector_ct=str(safe_get(log, "media_errors", default="N/A")),
        current_pending_sector="N/A",
        offline_uncorrectable="N/A",
        reallocated_event_count="N/A",
        ata_smart_error_log=str(safe_get(log, "num_err_log_entries", default="0")),
        self_test_status=_nvme_self_test_status(data),
        udma_crc_error_count="N/A",
        raw_read_error_rate="N/A",
        spin_retry_count="N/A",
        power_off_retract_count="N/A",
        load_cycle_count="N/A",
        helium_level="N/A",
    )


def _extract_ata_health(data: dict[str, Any]) -> SmartInfo:
    smart_passed = safe_get(data, "smart_status", "passed", default=False)
    smart_status = "PASSED" if smart_passed is True else "FAILED"

    return SmartInfo(
        model_family=str(safe_get(data, "model_family")),
        model_name=str(safe_get(data, "model_name")),
        serial_number=str(safe_get(data, "serial_number")),
        firmware_version=str(safe_get(data, "firmware_version")),
        user_capacity_bytes=_parse_capacity_bytes(data),
        user_capacity_gib=_parse_capacity_gib(data),
        rotation_rate=str(safe_get(data, "rotation_rate")),
        rotation_rate_display=rotation_display(str(safe_get(data, "rotation_rate"))),
        interface_speed=str(safe_get(data, "interface_speed", "current", "string")),
        power_on_time=str(safe_get(data, "power_on_time", "hours")),
        power_cycle_count=str(safe_get(data, "power_cycle_count")),
        smart_status=smart_status,
        temperature=str(safe_get(data, "temperature", "current")),
        endurance_used_percent=_ata_endurance_used(data),
        available_spare_percent=str(safe_get(data, "spare_available", "current_percent", default="N/A")),
        data_written_tib=_ata_data_written_tib(data),
        unsafe_shutdowns="N/A",
        pending_defects_count=_pending_defects_count(data),
        sata_phy_icrc_errors=_sata_phy_counter(data, _SATA_PHY_ICRC_ERROR),
        sata_phy_crc_errors=_sata_phy_counter(data, _SATA_PHY_CRC_ERROR),
        sata_phy_comreset_count=_sata_phy_counter(data, _SATA_PHY_COMRESET),
        scsi_uncorrected_errors="N/A",
        scsi_corrected_errors="N/A",
        scsi_sas_phy_errors="N/A",
        farm_unrecoverable_read_errors=_farm_value(
            data, ("page_3_error_statistics", "number_of_unrecoverable_read_errors")
        ),
        farm_unrecoverable_write_errors=_farm_value(
            data, ("page_3_error_statistics", "number_of_unrecoverable_write_errors")
        ),
        farm_read_recovery_attempts=_farm_value(data, ("page_3_error_statistics", "number_of_read_recovery_attempts")),
        farm_crc_errors=_farm_value(data, ("page_3_error_statistics", "total_crc_errors")),
        farm_head_flight_hours=_farm_value(data, ("page_1_drive_information", "head_flight_hours")),
        farm_head_load_events=_farm_value(data, ("page_1_drive_information", "head_load_events")),
        farm_reset_count=_farm_value(data, ("page_1_drive_information", "reset_count")),
        farm_temperature_max=_farm_value(data, ("page_4_environment_statistics", "highest_temp")),
        reallocated_sector_ct=_find_attr(data, "Reallocated_Sector_Ct"),
        current_pending_sector=_find_attr(data, "Current_Pending_Sector"),
        offline_uncorrectable=_find_attr(data, "Offline_Uncorrectable"),
        reallocated_event_count=_find_attr(data, "Reallocated_Event_Count"),
        ata_smart_error_log=_ata_error_log_count(data),
        self_test_status=str(safe_get(data, "ata_smart_data", "self_test", "status", "string")),
        udma_crc_error_count=_find_attr(data, "UDMA_CRC_Error_Count"),
        raw_read_error_rate=_find_attr(data, "Raw_Read_Error_Rate"),
        spin_retry_count=_find_attr(data, "Spin_Retry_Count"),
        power_off_retract_count=_find_attr(data, "Power-Off_Retract_Count"),
        load_cycle_count=_find_attr(data, "Load_Cycle_Count"),
        helium_level=_find_attr(data, "Helium_Level"),
    )


def _extract_scsi_health(data: dict[str, Any]) -> SmartInfo:
    smart_passed = safe_get(data, "smart_status", "passed", default=False)
    smart_status = "PASSED" if smart_passed is True else "FAILED"

    model_name = safe_get(data, "model_name", default=None)
    if model_name is None:
        model_name = safe_get(data, "scsi_model_name", default="N/A")
    firmware_version = safe_get(data, "firmware_version", default=None)
    if firmware_version is None:
        firmware_version = safe_get(data, "scsi_revision", default="N/A")

    return SmartInfo(
        model_family=str(safe_get(data, "model_family")),
        model_name=str(model_name),
        serial_number=str(safe_get(data, "serial_number")),
        firmware_version=str(firmware_version),
        user_capacity_bytes=_parse_capacity_bytes(data),
        user_capacity_gib=_parse_capacity_gib(data),
        rotation_rate=str(safe_get(data, "rotation_rate")),
        rotation_rate_display=rotation_display(str(safe_get(data, "rotation_rate"))),
        interface_speed=str(safe_get(data, "interface_speed", "current", "string", default=_scsi_link_rate(data))),
        power_on_time=str(safe_get(data, "power_on_time", "hours")),
        power_cycle_count=str(safe_get(data, "scsi_start_stop_cycle_counter", "accumulated_start_stop_cycles")),
        smart_status=smart_status,
        temperature=str(safe_get(data, "temperature", "current")),
        endurance_used_percent=str(safe_get(data, "scsi_percentage_used_endurance_indicator")),
        available_spare_percent="N/A",
        data_written_tib=_scsi_data_written_tib(data),
        unsafe_shutdowns="N/A",
        pending_defects_count="N/A",
        sata_phy_icrc_errors="N/A",
        sata_phy_crc_errors="N/A",
        sata_phy_comreset_count="N/A",
        scsi_uncorrected_errors=_scsi_error_sum(data, "total_uncorrected_errors"),
        scsi_corrected_errors=_scsi_error_sum(data, "total_errors_corrected"),
        scsi_sas_phy_errors=_scsi_sas_phy_errors(data),
        farm_unrecoverable_read_errors=_farm_value(
            data,
            ("page_3_error_statistics", "number_of_unrecoverable_read_errors"),
            ("error_statistics", "unrecoverable_read_errors"),
        ),
        farm_unrecoverable_write_errors=_farm_value(
            data,
            ("page_3_error_statistics", "number_of_unrecoverable_write_errors"),
            ("error_statistics", "unrecoverable_write_errors"),
        ),
        farm_read_recovery_attempts=_farm_value(data, ("page_3_error_statistics", "number_of_read_recovery_attempts")),
        farm_crc_errors=_farm_value(data, ("page_3_error_statistics", "total_crc_errors")),
        farm_head_flight_hours=_farm_value(data, ("page_1_drive_information", "head_flight_hours")),
        farm_head_load_events=_farm_value(data, ("page_1_drive_information", "head_load_events")),
        farm_reset_count=_farm_value(
            data,
            ("page_1_drive_information", "reset_count"),
            ("drive_information", "hardware_reset_count"),
        ),
        farm_temperature_max=_farm_value(
            data,
            ("page_4_environment_statistics", "highest_temp"),
            ("environment_statistics", "highest_temperature"),
        ),
        reallocated_sector_ct=str(safe_get(data, "scsi_grown_defect_list")),
        current_pending_sector="N/A",
        offline_uncorrectable="N/A",
        reallocated_event_count="N/A",
        ata_smart_error_log="N/A",
        self_test_status=_scsi_self_test_status(data),
        udma_crc_error_count="N/A",
        raw_read_error_rate="N/A",
        spin_retry_count="N/A",
        power_off_retract_count="N/A",
        load_cycle_count=str(safe_get(data, "scsi_start_stop_cycle_counter", "accumulated_load_unload_cycles")),
        helium_level="N/A",
    )


def _parse_capacity_bytes(data: dict[str, Any]) -> int:
    uc_bytes = safe_get(data, "user_capacity", "bytes", default=0)
    try:
        return int(uc_bytes)
    except (ValueError, TypeError):
        return 0


def _parse_capacity_gib(data: dict[str, Any]) -> float | None:
    uc_bytes = _parse_capacity_bytes(data)
    return round(uc_bytes / (2**30), 2) if uc_bytes > 0 else None


def extract_fields(data: dict[str, Any]) -> SmartInfo:
    """Extract key SMART health metrics from raw smartctl JSON output into a typed dict."""
    if "nvme_smart_health_information_log" in data:
        logging.debug("Extracting NVMe health fields")
        return _extract_nvme_health(data)
    if safe_get(data, "device", "protocol", default=None) == "SCSI":
        logging.debug("Extracting SCSI health fields")
        return _extract_scsi_health(data)
    logging.debug("Extracting ATA health fields")
    return _extract_ata_health(data)


def build_device_tree(
    pattern: str = ".*",
    sources: tuple[str, ...] = SOURCE_DIRS,
    exclude_patterns: list[str] | None = None,
) -> list[dict[str, object]]:
    """Scan ``/dev/disk/<source>/`` directories and map block devices to their identifiers.

    Each returned entry is a dict with keys:

    - ``device``: resolved block device path (e.g. ``/dev/sda``)
    - ``model``: model name from sysfs (or ``"N/A"``)
    - ``size_human``: human-readable size (e.g. ``"3.6 TiB"``)
    - ``size_bytes``: size in bytes
    - ``sources``: dict mapping source name (e.g. ``"by-id"``) to a sorted
      list of **full** symlink paths

    Partition entries and sources with no matching identifiers are excluded
    from the result.  Entries are sorted by device path.

    Raises:
        DiskNotFoundError: If the disk parent directory is missing, the regex
            is invalid, or no matching identifiers are found.
    """
    disk_dir = Path("/dev/disk")
    if not disk_dir.is_dir():
        raise DiskNotFoundError(f"Directory not found: {disk_dir}")

    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        raise DiskNotFoundError(f"Invalid regex pattern: {exc}") from exc

    exclude_compiled = _compile_excludes(exclude_patterns)

    _part_re = re.compile(r"-part\d+$")
    seen_devices: dict[str, dict[str, list[str]]] = {}
    excluded_targets: set[str] = set()
    available_sources: list[str] = []

    for source in sources:
        source_dir = disk_dir / source
        if not source_dir.is_dir():
            continue
        available_sources.append(source)
        for entry in sorted(source_dir.iterdir()):
            if not entry.is_symlink():
                continue
            name = entry.name
            if _part_re.search(name):
                continue
            if not compiled.search(name):
                continue
            target = str(entry.resolve())
            if exclude_compiled and is_excluded(name, target, exclude_compiled):
                excluded_targets.add(target)
                continue
            if not is_whole_disk(target):
                continue
            full_path = str(entry)
            seen_devices.setdefault(target, {}).setdefault(source, []).append(full_path)

    for target in excluded_targets:
        seen_devices.pop(target, None)

    if not seen_devices:
        detail = ""
        if not available_sources:
            detail = f" (no /dev/disk/ source directories found; checked: {', '.join(sources)})"
        raise DiskNotFoundError(f"No disk identifiers found matching pattern: {pattern}{detail}")

    result: list[dict[str, object]] = []
    for device in sorted(seen_devices):
        model, size_human, size_bytes = get_disk_info(device)
        result.append(
            {
                "device": device,
                "model": model,
                "size_human": size_human,
                "size_bytes": size_bytes,
                "sources": seen_devices[device],
            }
        )

    return result
