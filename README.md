# smartscan

[![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/ak1ra-lab/smartscan/.github%2Fworkflows%2Fpublish-to-pypi.yaml)](https://github.com/ak1ra-lab/smartscan/actions/workflows/publish-to-pypi.yaml)
[![PyPI - Version](https://img.shields.io/pypi/v/smartscan)](https://pypi.org/project/smartscan/)
[![PyPI - Version](https://img.shields.io/pypi/v/smartscan?label=test-pypi&pypiBaseUrl=https%3A%2F%2Ftest.pypi.org)](https://test.pypi.org/project/smartscan/)
[![Docs](https://img.shields.io/badge/docs-online-0a7ea4)](https://ak1ra-lab.github.io/smartscan/)

A CLI tool that runs smartctl on all disks, extracts key SMART health metrics, and stores historical results in SQLite for tracking changes over time.

## Installation

```bash
uv sync --group dev
```

## Usage

```bash
uv run smartscan info
```

## Development

```bash
just lint
just typecheck
just test
just docs-build
```

## Documentation

The published documentation site lives at <https://ak1ra-lab.github.io/smartscan/>, and local docs configuration is stored in `zensical.toml`.
