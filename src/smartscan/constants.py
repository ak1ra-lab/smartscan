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
    user_capacity_bytes INTEGER,
    user_capacity_gib REAL,
    rotation_rate TEXT,
    interface_speed TEXT,
    power_on_time_hours TEXT,
    power_cycle_count TEXT,
    temperature_celsius TEXT,
    reallocated_sector_ct TEXT,
    ata_smart_error_log_count TEXT,
    self_test_status TEXT,
    raw_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_smart_info_disk_ts
    ON smart_info(disk_path, timestamp);
"""
