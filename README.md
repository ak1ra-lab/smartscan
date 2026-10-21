# smartscan

[![CI](https://img.shields.io/github/actions/workflow/status/ak1ra-lab/smartscan/.github%2Fworkflows%2Fci.yaml?branch=master)](https://github.com/ak1ra-lab/smartscan/actions/workflows/ci.yaml)
[![PyPI - Version](https://img.shields.io/pypi/v/smartscan)](https://pypi.org/project/smartscan/)
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
sudo smartscan collect --no-save "WDC"
sudo smartscan collect --verbose
sudo smartscan --json collect
```

Query historical records, filter by name, or get JSON output:

```bash
smartscan query --since 2026-01-01
smartscan query --last-days 7 --verbose
```

Default tables show only fields that the drive actually reports and that are
relevant to its health. Use `--verbose` to include diagnostic counters and
unavailable fields as well.

Map disks to their /dev/disk/ identifiers (no root needed):

```bash
smartscan lsblk
smartscan lsblk --source by-id "Samsung"
smartscan --exclude '^/dev/(loop|zd)\d+' lsblk
```

Read the [full documentation](https://ak1ra-lab.github.io/smartscan/) for shell completion, configuration reference, and advanced usage.
