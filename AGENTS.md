# AGENTS.md

## What This Project Does

smartscan is a CLI tool that runs `smartctl` on all disk devices, extracts key SMART health metrics (temperature, reallocated sectors, power-on hours, etc.), and stores historical results in SQLite for tracking changes over time. It supports both interactive table output and JSON lines for scripting.

## Environment & Tooling — CRITICAL

- ALWAYS use `uv` for dependency management and command execution.
- Sync dependencies with `uv sync --group dev`.
- Run tests with `just test` or `uv run pytest -v tests/`.
- Lint and format with `just lint`; run static typing with `just typecheck`.
- Build docs with `just docs-build` and preview them with `just docs-serve`.
- DO NOT use ad hoc `pip install` commands instead of updating `pyproject.toml`.
- DO NOT edit generated output under `site/`; rebuild it from source.

## Conventions

- Application code lives under `src/smartscan`.
- The CLI uses stdlib `argparse` with `argcomplete` for shell completion. Subcommands: `collect` and `query`.
- Terminal output uses [Rich](https://rich.readthedocs.io/) for styled tables and formatting.
- Configuration uses [Pydantic](https://docs.pydantic.dev/) `BaseModel` for validation.
- SMART field structures use `TypedDict` (`SmartInfo`) for type safety.
- Custom exceptions (`SmartScanError` hierarchy) separate error handling from business logic — only `cli.py` calls `sys.exit()`.
- Tests live under `tests/` and should track public behavior, especially the CLI.
- Documentation source lives under `docs/`, and docs configuration lives in `zensical.toml`.
- Project metadata and dependency groups are defined in `pyproject.toml`; treat that file as the source of truth for tooling changes.

## Module Layout

| Module | Responsibility |
|---|---|
| `constants.py` | Default paths, DB schema, error messages |
| `exceptions.py` | `SmartScanError` hierarchy |
| `models.py` | `SmartScanConfig` (Pydantic), `SmartInfo` (TypedDict) |
| `config.py` | `load_config()` — read TOML config into `SmartScanConfig` |
| `logging.py` | `setup_logging()` |
| `smartctl.py` | `find_disks()`, `run_smartctl()`, `extract_fields()`, helpers |
| `output.py` | Rich-powered `print_table()`, `print_query_table()`, `print_json_output()` |
| `database.py` | SQLite init, open, save, query |
| `commands.py` | `do_collect()`, `do_query()` |
| `cli.py` | `create_parser()`, `main()` |

## Testing Guidelines

- Update tests when CLI behavior, public APIs, or package layout changes.
- Test the CLI via the `create_parser()` function or by invoking `main()` directly.
- Keep docs commands working when changing docs pages, API docs wiring, or navigation structure.

## Common Operations

```sh
uv sync --group dev       # sync development dependencies
just lint                          # lint and format source plus tests
just typecheck                     # run Astral ty over src/
just test                          # run the pytest suite
just docs-build                    # build the static docs site with Zensical
just docs-serve                    # preview docs locally on the configured dev address
```
