# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Initial release of the smartscan CLI tool.
- `collect` subcommand to gather SMART data from disk devices via `smartctl`.
- `query` subcommand to search historical SMART records in SQLite.
- Rich-powered terminal output with styled tables and warnings.
- JSON lines output mode for scripting.
- Pydantic-based TOML configuration with validation.
- Custom exception hierarchy (`SmartScanError`) for clean error handling.
- `SmartInfo` TypedDict for type-safe SMART field access.
