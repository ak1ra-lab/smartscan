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

_SYS_BLOCK = Path("/sys/class/block")
_PARTITION_NAME_RE = re.compile(
    r"^(?:sd[a-z]+\d+|hd[a-z]+\d+|vd[a-z]+\d+|xvd[a-z]+\d+"
    r"|nvme\d+n\d+p\d+"
    r"|mmcblk\d+p\d+"
    r"|loop\d+p\d+)"
    r"$"
)


_SOURCE_DIRS = ("by-id", "by-path", "by-diskseq")


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
        rotation_rate_display=_rotation_display(data),
        interface_speed=str(safe_get(data, "interface_speed", "current", "string")),
        power_on_time=str(safe_get(log, "power_on_hours", default="N/A")),
        power_cycle_count=str(safe_get(log, "power_cycles", default="N/A")),
        smart_status=smart_status,
        temperature=str(safe_get(log, "temperature", default="N/A")),
        reallocated_sector_ct=str(safe_get(log, "media_errors", default="N/A")),
        current_pending_sector="N/A",
        offline_uncorrectable="N/A",
        reallocated_event_count="N/A",
        ata_smart_error_log=str(safe_get(log, "num_err_log_entries", default="0")),
        self_test_status=str(safe_get(log, "self_test", "status", "string")),
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
        rotation_rate_display=_rotation_display(data),
        interface_speed=str(safe_get(data, "interface_speed", "current", "string")),
        power_on_time=str(safe_get(data, "power_on_time", "hours")),
        power_cycle_count=str(safe_get(data, "power_cycle_count")),
        smart_status=smart_status,
        temperature=str(safe_get(data, "temperature", "current")),
        reallocated_sector_ct=_find_attr(data, "Reallocated_Sector_Ct"),
        current_pending_sector=_find_attr(data, "Current_Pending_Sector"),
        offline_uncorrectable=_find_attr(data, "Offline_Uncorrectable"),
        reallocated_event_count=_find_attr(data, "Reallocated_Event_Count"),
        ata_smart_error_log=str(
            safe_get(data, "ata_smart_error_log", "summary", "count", default="0")
        ),
        self_test_status=str(
            safe_get(data, "ata_smart_data", "self_test", "status", "string")
        ),
        udma_crc_error_count=_find_attr(data, "UDMA_CRC_Error_Count"),
        raw_read_error_rate=_find_attr(data, "Raw_Read_Error_Rate"),
        spin_retry_count=_find_attr(data, "Spin_Retry_Count"),
        power_off_retract_count=_find_attr(data, "Power-Off_Retract_Count"),
        load_cycle_count=_find_attr(data, "Load_Cycle_Count"),
        helium_level=_find_attr(data, "Helium_Level"),
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


def _rotation_display(data: dict[str, Any]) -> str:
    rotation_rate = str(safe_get(data, "rotation_rate"))
    if rotation_rate not in ("N/A", "0"):
        return f"{rotation_rate} rpm"
    return "SSD (no rotation)"


def extract_fields(data: dict[str, Any]) -> SmartInfo:
    """Extract key SMART health metrics from raw smartctl JSON output into a typed dict."""
    if "nvme_smart_health_information_log" in data:
        return _extract_nvme_health(data)
    return _extract_ata_health(data)


def _is_whole_disk(dev_path: str | Path) -> bool:
    name = Path(dev_path).name
    part_file = _SYS_BLOCK / name / "partition"
    try:
        return part_file.read_text().strip() == "0"
    except (OSError, FileNotFoundError):
        return not bool(_PARTITION_NAME_RE.match(name))


def _format_size(size_bytes: int) -> str:
    if size_bytes <= 0:
        return "N/A"
    units = ("B", "KiB", "MiB", "GiB", "TiB", "PiB")
    value = float(size_bytes)
    for unit in units:
        if abs(value) < 1024.0:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024.0
    return f"{value:.1f} PiB"


def _get_disk_info(dev_path: str) -> tuple[str, str, int]:
    name = Path(dev_path).name
    sys_dir = _SYS_BLOCK / name

    model = "N/A"
    model_file = sys_dir / "device" / "model"
    try:
        model = model_file.read_text().strip()
    except (OSError, FileNotFoundError):
        pass

    size_bytes = 0
    size_file = sys_dir / "size"
    try:
        sectors = int(size_file.read_text().strip())
        size_bytes = sectors * 512
    except (OSError, FileNotFoundError, ValueError):
        pass

    size_human = _format_size(size_bytes)
    return model, size_human, size_bytes


def build_device_tree(
    pattern: str = ".*",
    sources: tuple[str, ...] = _SOURCE_DIRS,
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

    exclude_compiled: list[re.Pattern[str]] = []
    if exclude_patterns:
        for ep in exclude_patterns:
            try:
                exclude_compiled.append(re.compile(ep))
            except re.error as exc:
                raise DiskNotFoundError(
                    f"Invalid exclude regex pattern: {exc}"
                ) from exc

    _part_re = re.compile(r"-part\d+$")
    seen_devices: dict[str, dict[str, list[str]]] = {}
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
            if exclude_compiled and any(exc.search(target) for exc in exclude_compiled):
                continue
            if not _is_whole_disk(target):
                continue
            full_path = str(entry)
            seen_devices.setdefault(target, {}).setdefault(source, []).append(full_path)

    if not seen_devices:
        detail = ""
        if not available_sources:
            detail = f" (no /dev/disk/ source directories found; checked: {', '.join(sources)})"
        raise DiskNotFoundError(
            f"No disk identifiers found matching pattern: {pattern}{detail}"
        )

    result: list[dict[str, object]] = []
    for device in sorted(seen_devices):
        model, size_human, size_bytes = _get_disk_info(device)
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
