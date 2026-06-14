"""Pydantic configuration model and TypedDict for SMART data structures."""

from __future__ import annotations

from typing import Literal, TypedDict

from pydantic import BaseModel, Field

from .constants import DEFAULT_DB_PATH, DEFAULT_LOG_FILE, DEFAULT_SYSTEM_PROMPT


class SmartInfo(TypedDict):
    model_family: str
    model_name: str
    serial_number: str
    firmware_version: str
    user_capacity_bytes: int
    user_capacity_gib: float | None
    rotation_rate: str
    rotation_rate_display: str
    interface_speed: str
    power_on_time: str
    power_cycle_count: str
    smart_status: str
    temperature: str
    reallocated_sector_ct: str
    current_pending_sector: str
    offline_uncorrectable: str
    reallocated_event_count: str
    ata_smart_error_log: str
    self_test_status: str
    udma_crc_error_count: str
    raw_read_error_rate: str
    spin_retry_count: str
    power_off_retract_count: str
    load_cycle_count: str
    helium_level: str


class ThresholdRules(BaseModel):
    enabled: bool = True
    temperature_celsius: int = 50
    reallocated_sector_ct: int = 0
    current_pending_sector: int = 0
    offline_uncorrectable: int = 0
    reallocated_event_count: int = 0
    udma_crc_error_count: int = 0
    ata_smart_error_log_count: int = 0
    spin_retry_count: int = 0
    load_cycle_count: int = 600_000


class LLMConfig(BaseModel):
    enabled: bool = False
    provider: Literal["openai", "anthropic"] = "openai"
    api_url: str = "https://api.openai.com/v1/chat/completions"
    api_key: str = ""
    model: str = "gpt-4o-mini"
    max_tokens: int = 4096
    timeout: int = 120
    temperature: float = 0.3
    delay: float = 0.0
    system_prompt: str = DEFAULT_SYSTEM_PROMPT


class CollectConfig(BaseModel):
    no_save: bool = False


class QueryConfig(BaseModel):
    since: str | None = None
    until: str | None = None
    last_days: int | None = None


class LsblkConfig(BaseModel):
    source: list[str] = Field(default_factory=list)


class SmartScanConfig(BaseModel):
    format: Literal["table", "json"] = "table"
    db_path: str = DEFAULT_DB_PATH
    log_file: str = DEFAULT_LOG_FILE
    exclude_patterns: list[str] = Field(default_factory=list)
    collect: CollectConfig = Field(default_factory=CollectConfig)
    query: QueryConfig = Field(default_factory=QueryConfig)
    lsblk: LsblkConfig = Field(default_factory=LsblkConfig)
    thresholds: ThresholdRules = Field(default_factory=ThresholdRules)
    llm: LLMConfig = Field(default_factory=LLMConfig)
