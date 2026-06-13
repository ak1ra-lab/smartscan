# smartscan

[![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/ak1ra-lab/smartscan/.github%2Fworkflows%2Fpublish-to-pypi.yaml)](https://github.com/ak1ra-lab/smartscan/actions/workflows/publish-to-pypi.yaml)
[![PyPI - Version](https://img.shields.io/pypi/v/smartscan)](https://pypi.org/project/smartscan/)
[![PyPI - Version](https://img.shields.io/pypi/v/smartscan?label=test-pypi&pypiBaseUrl=https%3A%2F%2Ftest.pypi.org)](https://test.pypi.org/project/smartscan/)
[![Docs](https://img.shields.io/badge/docs-online-0a7ea4)](https://ak1ra-lab.github.io/smartscan/)

A CLI tool that runs smartctl on all disks, extracts key SMART health metrics, and stores historical results in SQLite for tracking changes over time.

## Quick start

Install [smartmontools](https://www.smartmontools.org/) to provide the `smartctl` command, then install smartscan:

```bash
uv tool install smartscan
```

Collect SMART data from all disks (requires root):

```bash
sudo smartscan collect
sudo smartscan collect "WDC"
sudo smartscan --json collect
```

Query historical records, filter by name, or get JSON output:

```bash
smartscan query --since 2026-01-01
```

Map disks to their /dev/disk/ identifiers (no root needed):

```bash
smartscan identify
smartscan identify --source by-id "Samsung"
```

Read the [full documentation](https://ak1ra-lab.github.io/smartscan/) for shell completion, configuration reference, and advanced usage.
