# smartscan

A CLI tool that runs smartctl on all disks, extracts key SMART health metrics, and stores historical results in SQLite for tracking changes over time.

## Highlights

- Collects SMART data via `smartctl --all --json` from `/dev/disk/by-id/ata-*`.
- Displays results as Rich-styled tables with warnings for critical values.
- Stores historical data in SQLite for trend analysis (`query` subcommand).
- Supports JSON lines output for scripting.
- Configurable via TOML config file with Pydantic validation.
- Built with `uv`, `ruff`, `ty`, `pytest`, and `zensical`.
- CLI uses `argparse` and `argcomplete` for shell completion.

## Quick start

```bash
uv sync --group dev
uv run smartscan collect
```
