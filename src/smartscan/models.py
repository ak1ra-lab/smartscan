"""Pydantic configuration model and TypedDict for SMART data structures."""

from __future__ import annotations

from typing import Literal, TypedDict

from pydantic import BaseModel

from .constants import DEFAULT_DB_PATH, DEFAULT_LOG_FILE


class SmartInfo(TypedDict):
    model_family: str
    model_name: str
    user_capacity_bytes: int
    user_capacity_gib: float | None
    rotation_rate: str
    rotation_rate_display: str
    interface_speed: str
    power_on_time: str
    power_cycle_count: str
    temperature: str
    reallocated_sector_ct: str
    ata_smart_error_log: str
    self_test_status: str


class SmartScanConfig(BaseModel):
    format: Literal["table", "json"] = "table"
    no_save: bool = False
    no_log_file: bool = False
    db_path: str = DEFAULT_DB_PATH
    log_file: str = DEFAULT_LOG_FILE
