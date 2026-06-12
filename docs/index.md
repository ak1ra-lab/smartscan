# smartscan

A CLI tool that runs smartctl on all disks, extracts key SMART health metrics, and stores historical results in SQLite for tracking changes over time.

## Highlights

- Built with `uv`, `ruff`, `ty`, `pytest`, and `zensical`.
- CLI uses `argparse` and `argcomplete` for shell completion.
- Packaged from `src/smartscan`.
- Published documentation lives at <https://ak1ra-lab.github.io/smartscan/>.

## Quick start

```bash
uv sync --group dev
uv run smartscan info
```
