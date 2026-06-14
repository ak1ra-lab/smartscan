# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
