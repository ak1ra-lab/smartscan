"""Shared result types for collected disk data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import SmartInfo
from .thresholds import Alert


@dataclass
class DiskEntry:
    """SMART data and derived state for one disk during a ``collect`` run."""

    disk_name: str
    disk_path: str
    fields: SmartInfo | None
    alerts: list[Alert]
    data: dict[str, Any] | None
    returncode: int
    llm_analysis: str | None = None
