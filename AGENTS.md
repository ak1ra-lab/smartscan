# AGENTS.md

## What This Project Does

This repository is a Python project generated from the `copier-pyproject` template. It uses an Astral-centered toolchain for packaging, linting, type checking, testing, and documentation. See `README.md` for user-facing setup and publishing details.

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
- The CLI uses stdlib `argparse` with `argcomplete` for shell completion.
- Tests live under `tests/` and should track public behavior, especially the CLI.
- Documentation source lives under `docs/`, and docs configuration lives in `zensical.toml`.
- Project metadata and dependency groups are defined in `pyproject.toml`; treat that file as the source of truth for tooling changes.

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
