# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Default `collect` and `query` tables now omit fields the drive does not report instead of printing `N/A`; `--verbose` still shows every field, including unavailable values
- Extended fields that trigger a threshold alert are promoted into the default table so warnings are never hidden
- LLM prompts now include every extracted field and, for per-disk and batch analysis, the complete raw `smartctl` JSON; trend analysis includes the latest complete field set
- Raise the default `llm.max_tokens` from 4096 to 8192 so batch summaries and reasoning outputs have more room; it remains an output cap and does not affect input/context size

### Fixed

- Alert highlighting now looks up fields by their underlying key instead of their display label
- Unknown rotation rates are no longer reported as `SSD (no rotation)`

## [0.6.0] - 2026-10-21

### Added

- Extract NVMe endurance used, available spare, data written, and unsafe shutdowns from the SMART/Health log
- Extract ATA endurance and data-written values from Device Statistics collected by `--xall`
- Extract ATA pending-defect counts and SATA PHY ICRC/CRC/COMRESET counters
- Discover and extract SCSI/SAS disks, including grown defects, error counters, start-stop cycles, link rate, and SAS PHY errors
- Collect the Seagate FARM log when a drive reports support and extract unrecoverable read/write errors, read recovery attempts, CRC errors, head flight/load counters, reset count, and maximum temperature
- Add `thresholds.endurance_used_percent` (default `90`) and thresholds for pending defects, SATA PHY, SCSI, and FARM errors

### Changed

- Collect with `smartctl --xall --json` instead of `--all --json`; ATA disks now include device statistics, pending defects, SATA PHY counters, and extended error/self-test logs

### Fixed

- ATA error-log counts are read from the extended log when available, falling back to the summary log
- NVMe self-test status is read from `nvme_self_test_log` instead of the SMART/Health log
- In-progress self-tests no longer raise a false warning
- NVMe interface speed is read from sysfs when smartctl does not report it
- SATA disks behind a SCSI/SAS HBA are retried with `-d sat` when auto-detection returns no usable SMART data
- Querying a database created by an older version no longer fails when newer columns are missing
- `N/A` values no longer render with units in tables and LLM prompts

## [0.5.0] - 2026-10-21

### Changed

- Invalid or unreadable config files now abort with an error instead of silently falling back to defaults
- `lsblk.source` values are validated against `by-id`, `by-path`, and `by-diskseq`
- Replace Zensical with MkDocs Material for the documentation site

### Fixed

- Feishu webhook signatures now follow the documented `timestamp\nsecret` HMAC-SHA256 algorithm
- Self-test statuses containing a failure (e.g. `Completed: read failure`) are no longer treated as healthy
- `lang = "zh"` now works as documented, in addition to `zh-CN` and `zh-TW`
- Log-file creation errors are written to stderr instead of corrupting JSON output on stdout
- `query` now reports a missing database file instead of exiting silently

## [0.4.0] - 2026-06-26

### Added

- Notification channels: Telegram, DingTalk, and Feishu webhook notifiers for SMART health alerts and LLM analysis
- `prune` subcommand for removing redundant unchanged records within a time window; supports `--dry-run` and `--force`
- Query compaction: automatically deduplicate similar records within a 30-minute window; disable with `--no-compact`
- `query --trend` for LLM-powered trend analysis across historical records
- `LLMConfig.lang` for localized LLM responses (e.g., `"zh"`)
- LLM API key resolution from environment variables (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`)
- Smartctl error bit descriptions included in LLM prompt for better diagnosis of failed runs
- `log_level` config key and `--log-level` CLI argument for configurable log verbosity

### Changed

- `--force-llm` and `--batch-llm` replaced by `--llm {all,summary,off}` (**breaking**: update CLI invocations)
- Logging writes to file only; stderr reserved for fatal errors displayed with `print()` (**breaking**: stderr output changed)
- `DEFAULT_CONFIG_PATH` replaced with `CONFIG_SEARCH_PATHS` searching XDG user dir then system path (**breaking**: config location may differ)
- Module layout: `llm.py` split into `llm/` package; `notifications.py` into `notifications/` package; generic utilities extracted to `utils.py`
- `setup_logging()` supports reconfiguration and boots with `NullHandler` before config is loaded

### Fixed

- `smartctl` negative return codes from signal termination handled correctly

## [0.3.1] - 2026-06-14

### Fixed

- Exclude entire device in `build_device_tree` when any symlink entry matches the pattern

## [0.3.0] - 2026-06-14

### Added

- Global `--exclude` option usable by `collect` and `lsblk` subcommands
- `exclude_patterns` top-level config key shared across subcommands
- Exclude patterns now match both symlink names and resolved target paths

### Changed

- `identify` subcommand renamed to `lsblk` (**breaking**: CLI invocation changes)
- `exclude_patterns` config key removed from `[lsblk]` section; use top-level key instead (**breaking**: update TOML config)
- Extracted `fields.py` and `llm.py` into dedicated modules

## [0.2.0] - 2026-06-13

### Added

- `identify` subcommand for listing disk devices from `/dev/disk/by-*` with resolved device paths
- `--exclude` flag for `identify` to filter devices by regex pattern against resolved paths
- `--last-days` flag for `query` to restrict results to recent days
- Anthropic API provider support (`provider = "anthropic"`) for LLM health analysis
- `exclude_patterns` field in `[identify]` config; `last_days`, `since`, `until` in `[query]`

### Changed

- Configuration restructured into sub-models: `[collect]`, `[query]`, `[identify]`
  `no_save` moved under `[collect]` (breaking change: update TOML config)
- Documentation split into separate pages: `configuration.md` and `llm-examples.md`

### Fixed

- Anthropic response parsing now handles `thinking` blocks and proxies returning `"content"` instead of `"text"`
- LLM `api_key` no longer validated as required, allowing local endpoints without authentication

## [0.1.0] - 2026-06-13

### Added

- CLI tool with `collect` and `query` subcommands for SMART disk health monitoring
- SMART data collection via `smartctl --all --json` from `/dev/disk/by-id/`
- SQLite history database with WAL mode, auto-migration, and date-range query filters
- Rich-powered table output with styled headers and colour-coded alert rows
- JSON lines output mode for scripting (`--json`)
- Pydantic-based TOML configuration for thresholds, LLM, and output preferences
- Custom exception hierarchy (`SmartScanError`) separating error handling from `sys.exit()`
- Shell tab completion via `argcomplete`
- Configurable threshold-based SMART health alerts (temperature, reallocated sectors, pending sectors, UDMA CRC errors, load cycles, etc.)
- Optional LLM-based health analysis with configurable endpoint, model, temperature, and system prompt
- Force LLM analysis on all disks with `--force-llm`, bypassing both config and threshold checks
- Self-test recency check in the default LLM system prompt
- NVMe disk discovery with `/dev/disk/by-id/` deduplication (prefers vendor names over EUI identifiers, drops partition entries)
- NVMe health metric extraction from `nvme_smart_health_information_log` (`media_errors`, `num_err_log_entries`, `power_on_hours`, `power_cycles`, etc.)
- Verbose output mode (`-v`/`--verbose`) exposing extended fields (`raw_read_error_rate`, `spin_retry_count`, `load_cycle_count`, `helium_level`, etc.)

### Changed

- Removed `--no-log-file` option and default-subcommand fallback; logging now always writes to the configured log file
- Refactored health field extraction into separate `_extract_nvme_health()` and `_extract_ata_health()` functions

### Fixed

- Threshold checks now also run in `query` mode for historical alert display
- Database migration errors are now logged with a warning instead of being silently swallowed, except for expected "duplicate column" cases
- Docker image now installs `smartmontools` so the `smartctl` binary is available at run time
