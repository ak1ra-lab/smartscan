"""Generic utilities reusable across projects: disk introspection, config helpers, etc."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

_SYS_BLOCK = Path("/sys/class/block")
_SECTOR_BYTES = 512

_PARTITION_NAME_RE = re.compile(
    r"^(?:sd[a-z]+\d+|hd[a-z]+\d+|vd[a-z]+\d+|xvd[a-z]+\d+"
    r"|nvme\d+n\d+p\d+"
    r"|mmcblk\d+p\d+"
    r"|loop\d+p\d+)"
    r"$"
)

_ENV_VAR_RE = re.compile(r"\$\{(\w+)\}")


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


def expand_env_vars(obj: Any) -> Any:
    """Recursively expand ``${VAR}`` patterns in dicts, lists, and strings."""
    if isinstance(obj, dict):
        return {k: expand_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [expand_env_vars(v) for v in obj]
    if isinstance(obj, str):
        return _ENV_VAR_RE.sub(lambda m: os.environ.get(m.group(1), ""), obj)
    return obj


def compile_exclude_patterns(patterns: list[str] | None) -> list[re.Pattern[str]]:
    """Compile and return a list of exclusion regex patterns.

    Raises:
        ValueError: If a pattern is invalid.
    """
    if not patterns:
        return []
    compiled: list[re.Pattern[str]] = []
    for ep in patterns:
        try:
            compiled.append(re.compile(ep))
        except re.error as exc:
            raise ValueError(f"Invalid exclude regex pattern: {exc}") from exc
    return compiled


def is_excluded(
    name: str, target: str, exclude_compiled: list[re.Pattern[str]]
) -> bool:
    """Return ``True`` if *name* or *target* matches any compiled exclude pattern."""
    return any(exc.search(name) or exc.search(target) for exc in exclude_compiled)


def is_whole_disk(dev_path: str | Path) -> bool:
    """Return ``True`` if the block device is a whole disk (not a partition).

    Checks sysfs ``/sys/class/block/<name>/partition`` first,
    then falls back to a partition naming heuristic.
    """
    name = Path(dev_path).name
    part_file = _SYS_BLOCK / name / "partition"
    try:
        return part_file.read_text().strip() == "0"
    except (OSError, FileNotFoundError):
        return not bool(_PARTITION_NAME_RE.match(name))


def format_size(size_bytes: int) -> str:
    """Return a human-readable size string (e.g. ``"3.6 TiB"``)."""
    if size_bytes <= 0:
        return "N/A"
    units = ("B", "KiB", "MiB", "GiB", "TiB", "PiB")
    value = float(size_bytes)
    for unit in units:
        if abs(value) < 1024.0:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024.0
    return f"{value:.1f} PiB"


def get_disk_info(dev_path: str) -> tuple[str, str, int]:
    """Read model name and size from sysfs for a block device.

    Returns a tuple of ``(model, size_human, size_bytes)``.
    """
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
        size_bytes = sectors * _SECTOR_BYTES
    except (OSError, FileNotFoundError, ValueError):
        pass

    size_human = format_size(size_bytes)
    return model, size_human, size_bytes
