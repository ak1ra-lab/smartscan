"""Default paths, database schema, and error message constants."""

DEFAULT_DB_PATH = "~/.local/share/smartscan/smartscan.db"
DEFAULT_LOG_FILE = "~/.local/state/smartscan/smartscan.log"
DEFAULT_CONFIG_PATH = "~/.config/smartscan/smartscan.toml"

SMARTCTL_ERROR_MSGS = [
    "Bit 0: Command line did not parse.",
    "Bit 1: Device open failed, device did not return an IDENTIFY DEVICE structure, or device is in a low-power mode.",
    "Bit 2: Some SMART or other ATA command to the disk failed, or there was a checksum error in a SMART data structure.",
    "Bit 3: SMART status check returned 'DISK FAILING'.",
    "Bit 4: We found prefail Attributes <= threshold.",
    "Bit 5: SMART status check returned 'DISK OK' but we found that some (usage or prefail) Attributes have been <= threshold at some time in the past.",
    "Bit 6: The device error log contains records of errors.",
    "Bit 7: The device self-test log contains records of errors. [ATA only] Failed self-tests outdated by a newer successful extended self-test are ignored.",
]

DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS smart_info (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    disk_name TEXT NOT NULL,
    disk_path TEXT NOT NULL,
    model_family TEXT,
    model_name TEXT,
    serial_number TEXT,
    firmware_version TEXT,
    user_capacity_bytes INTEGER,
    user_capacity_gib REAL,
    rotation_rate TEXT,
    interface_speed TEXT,
    power_on_time_hours TEXT,
    power_cycle_count TEXT,
    smart_status TEXT,
    temperature_celsius TEXT,
    reallocated_sector_ct TEXT,
    current_pending_sector TEXT,
    offline_uncorrectable TEXT,
    reallocated_event_count TEXT,
    ata_smart_error_log_count TEXT,
    self_test_status TEXT,
    udma_crc_error_count TEXT,
    raw_read_error_rate TEXT,
    spin_retry_count TEXT,
    power_off_retract_count TEXT,
    load_cycle_count TEXT,
    helium_level TEXT,
    raw_json TEXT,
    llm_analysis TEXT
);
CREATE INDEX IF NOT EXISTS idx_smart_info_disk_ts
    ON smart_info(disk_path, timestamp);
"""

DB_MIGRATIONS = [
    "ALTER TABLE smart_info ADD COLUMN serial_number TEXT",
    "ALTER TABLE smart_info ADD COLUMN firmware_version TEXT",
    "ALTER TABLE smart_info ADD COLUMN smart_status TEXT",
    "ALTER TABLE smart_info ADD COLUMN current_pending_sector TEXT",
    "ALTER TABLE smart_info ADD COLUMN offline_uncorrectable TEXT",
    "ALTER TABLE smart_info ADD COLUMN reallocated_event_count TEXT",
    "ALTER TABLE smart_info ADD COLUMN udma_crc_error_count TEXT",
    "ALTER TABLE smart_info ADD COLUMN raw_read_error_rate TEXT",
    "ALTER TABLE smart_info ADD COLUMN spin_retry_count TEXT",
    "ALTER TABLE smart_info ADD COLUMN power_off_retract_count TEXT",
    "ALTER TABLE smart_info ADD COLUMN load_cycle_count TEXT",
    "ALTER TABLE smart_info ADD COLUMN helium_level TEXT",
    "ALTER TABLE smart_info ADD COLUMN llm_analysis TEXT",
]

DEFAULT_SYSTEM_PROMPT = """\
You are a hard drive health diagnostic expert analyzing SMART data.
Examine the provided SMART attributes and give a concise assessment:

1. Overall health status: HEALTHY / WARNING / CRITICAL
2. Key concerns with specific metric values (if any)
3. Recommended action (one sentence)

Be factual and conservative. Do not cause unnecessary alarm for borderline values.
If all metrics are within normal ranges, state the drive is healthy.
If you cannot make a definitive assessment, say so honestly."""
